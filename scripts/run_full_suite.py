"""run_full_suite.py — the ordered, folder-in → all-green-out test battery.

Point it at a report tree (default D:/Devs/Reports/Final_Data); it excludes the
quarantine folders (_wrong_format, _misfiled*, _duplicates, need review*), batch
extracts on up to 18 cores, then runs the ordered stages:

    S0 EXTRACT   every file parses (0 _extract_error; poison-safe serial retry)
    S1 HEADER    detected_format stable · no new unmapped headers · hard-required
                 fields (party_name/product_name) not newly empty
    S2 TRIAGE    4-state verdict per file; dashboard.html + SUMMARY.md refreshed;
                 no file's badge WORSENS vs the committed verdict baseline
    S3 PRODUCT   product-master match-rate not below baseline − 2pp; pack peel
                 NEVER truncates a name to a bare brand (absolute invariant)
    S4 ROWS      line-ledger completeness: line_unexplained not above baseline,
                 row_count not below, no NEW would-fire files
    S5 META      pytest units + pack_match standalone + regression suites +
                 mirror drift + cross-tree script identity (whatever exists here)

"Never fails again" mechanism: tests/full_suite_verdicts.json pins one verdict
row per file (badge, master_match, row_count, line_unexplained, ...). Gates are
DIRECTIONAL — improvements pass silently, any worsening fails and lists the
file. `--seed-baseline` writes it the first time; `--update-baseline` refreshes
after a verified improvement (same discipline as regression --update: never to
hide a live failure). Exact-value pinning stays owned by regression_test.py
(S5); this layer owns the verdict trajectory and covers files regression
doesn't.

Runs IDENTICALLY in Python-Service-UI and Backends (imports only core/ +
extractors/ + the mirrored scripts batch_extract/batch_core/render_dashboard/
regression_test). Outputs under <root>/_full_suite/<runid>/: dashboard.html,
SUMMARY.md, failures.json (the multi-agent verification worklist — see
MASTER_FULL_SUITE_PROMPT.md), triage_rows.json, run.json.

Usage:
    python scripts/run_full_suite.py                       # Final_Data, all stages
    python scripts/run_full_suite.py --folder <dir> --seed-baseline
    python scripts/run_full_suite.py --only-under "A TO Z" --skip-s5   # smoke
    python scripts/run_full_suite.py --selftest            # prove the gates fire
"""
from __future__ import annotations

import argparse
import filecmp
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import batch_extract as be          # noqa: E402  (mirrored: both trees)
import batch_core as bc             # noqa: E402  (mirrored: both trees)
import render_dashboard as rd       # noqa: E402  (mirrored: both trees)
from core.pack_match import extract_pack_from_product  # noqa: E402
from core.triage import HARD_REQUIRED_DATA             # noqa: E402

DEFAULT_ROOT = r"D:/Devs/Reports/Final_Data"
BASELINE_PATH = ROOT / "tests" / "full_suite_verdicts.json"

# 4-state badge rank: index into render_dashboard.BADGE (best -> worst).
_BADGE_RANK = {key: i for i, (key, *_rest) in enumerate(rd.BADGE)}

# Quarantine folders — never live report slots (mirrors run_batch.discover_folder
# + relocate_misfiled_reports.EXCLUDE_DIRS, plus the _duplicates variants).
_EXCLUDE_SUBSTR = ("need review", "need reviews", "need-review",
                   "_misfiled", "_wrong_format", "_duplicates")

# Dosage-form words a peeled pack must never end with (mirrors
# tests/test_pack_match.py NAME_FORMS — the pack invariant oracle).
_NAME_FORMS = {
    "LOTION", "CREAM", "GEL", "SOAP", "OINTMENT", "OINT", "SYRUP", "SYP",
    "SUSPENSION", "SUSP", "DROPS", "DROP", "BAR", "POWDER", "SERUM", "EMULGEL",
    "SHAMPOO", "FACEWASH", "TABLET", "TABLETS", "CAPSULE", "CAPSULES",
    "SOLUTION", "SPRAY", "CRE", "SOA", "LOT", "PES",
}


# --------------------------------------------------------------------------- #
# discovery (mirrors run_batch.route_for_path / discover_folder)
# --------------------------------------------------------------------------- #
def route_for_path(path: Path) -> str:
    ext = path.suffix.lower()
    is_xlsx = ext in (".xls", ".xlsx", ".xlsm")
    for anc in path.parents:
        n = anc.name.strip().lower()
        if n.endswith(("party report", "party reports", "party file", "party files")):
            return "party_xlsx" if is_xlsx else "party_pdf"
        if n.endswith(("stock report", "stock reports", "stock file", "stock files")):
            return "stock_xlsx" if is_xlsx else "stock_pdf"
    s = str(path).lower()
    party_hint = ("party wise" in s) or ("party_wise" in s) or ("party_product" in s)
    stock_hint = ("sales and stock" in s) or ("stock and sales" in s) or ("stock_sales" in s)
    if party_hint and not stock_hint:
        return "party_xlsx" if is_xlsx else "party_pdf"
    return "stock_xlsx" if is_xlsx else "stock_pdf"


def discover(root: Path, only_under: str = "", limit: int = 0):
    """(route, Path) for every live report file under root, quarantines skipped."""
    exts = be.PDF_EXTS | be.XLSX_EXTS
    jobs = []
    for f in sorted(root.rglob("*")):
        if not f.is_file() or f.suffix.lower() not in exts:
            continue
        low = str(f).lower()
        if any(seg in low for seg in _EXCLUDE_SUBSTR):
            continue
        if "wrong" in {p.lower() for p in f.parts}:
            continue
        if only_under and only_under.lower() not in low:
            continue
        jobs.append((route_for_path(f), f))
        if limit and len(jobs) >= limit:
            break
    return jobs


def file_key(path: Path) -> str:
    """stockist/slot/file — byte-identical to regression's unique_key join."""
    return "/".join(path.parts[-3:])


# --------------------------------------------------------------------------- #
# the one parallel analysis pass (module-level worker: Windows spawn safe)
# --------------------------------------------------------------------------- #
def _bad_pack(pack: str) -> bool:
    """mirrors tests/test_pack_match._is_bad_pack: pack with no digit, or ending
    in a dosage-form word, is a name-truncating peel — never allowed."""
    if not pack:
        return False
    if not re.search(r"\d", pack):
        return True
    words = re.findall(r"[A-Za-z]+", pack)
    return bool(words) and words[-1].upper() in _NAME_FORMS


def analyze_one(job):
    """(route, vendor, file_name, path_str) -> one combined per-file record.

    Reloads the cached extraction (fast disk read after S0) and derives, in ONE
    build_quality pass (inside bc.triage_row): the 4-state triage verdict, the
    ledger completeness fields, plus the header/product/pack stage inputs.
    """
    route, vendor, file_name, path_str = job
    try:
        result = be.get(route, path_str)
    except Exception as exc:  # defensive: never let one bad file kill the pass
        result = {"_extract_error": f"{type(exc).__name__}: {exc}"}
    row = bc.triage_row(route, vendor, file_name, path_str, result)
    rtype = bc.report_type(route)

    # S1 inputs — header health
    debug = result.get("debug") or {}
    row["detected_format"] = debug.get("detected_format") or debug.get("layout") or ""
    try:
        unmapped = bc.analyze_unmapped_headers(result, rtype)
    except Exception:
        unmapped = []
    row["unmapped_headers"] = len(unmapped)
    row["unmapped_header_names"] = [u.get("header", "") for u in unmapped[:5]]
    rows = result.get("rows") or []
    hard_rate = 0.0
    if rows:
        for field in HARD_REQUIRED_DATA.get(rtype, []):
            empty = sum(1 for r in rows if not str(r.get(field) or "").strip())
            hard_rate = max(hard_rate, empty / len(rows))
    row["hard_empty_rate"] = round(hard_rate, 4)

    # S3 inputs — pack invariant on the RAW names (enrichment rewrites
    # product_name to canonical and would mask the peel behaviour)
    violations = []
    for r in rows:
        s = str(r.get("raw_product_name") or r.get("product_name") or "").strip()
        if not s:
            continue
        try:
            base, pack = extract_pack_from_product(s)
        except Exception:
            continue
        if _bad_pack(pack) or (pack and not base):
            if len(violations) < 5:
                violations.append(f"{s!r}->({base!r},{pack!r})")
    row["pack_violations"] = len(violations)
    row["pack_violation_samples"] = violations

    # S4 evidence — unexplained sample lines for the agent pass
    la = result.get("line_audit") or {}
    row["line_unexplained_sample"] = (la.get("unexplained_sample") or [])[:3]
    return row


def _clusters(rows):
    """clone of run_batch.Runner._clusters (PSUI-only module) for the dashboard."""
    groups = {}
    for r in rows:
        if r["bucket"] == "GREEN":
            continue
        key = (r["route"], r["layout"], r["reason_code"])
        g = groups.setdefault(key, {"route": r["route"], "layout": r["layout"],
                                    "reason_code": r["reason_code"], "count": 0,
                                    "buckets": Counter(), "example": r["file_name"]})
        g["count"] += 1
        g["buckets"][r["bucket"]] += 1
    out = []
    for g in groups.values():
        g["buckets"] = dict(g["buckets"])
        g.update(bc.fix_meta(g["reason_code"]))
        out.append(g)
    out.sort(key=lambda g: (g["count"] * (1.0 if g["code_fixable"] else 0.4)), reverse=True)
    return out


# --------------------------------------------------------------------------- #
# gates
# --------------------------------------------------------------------------- #
def _fail(failures, stage, kind, row, baseline, actual, evidence=None):
    failures.append({
        "stage": stage, "kind": kind, "file_key": row["_key"], "path": row["path"],
        "route": row["route"], "layout": row.get("layout"),
        "baseline": baseline, "actual": actual, "evidence": evidence or {},
    })


def run_gates(rows, baseline, strict_new=False):
    """Directional worsening gates vs the verdict baseline. Returns
    (failures, new_files, gates_status). All stages evaluate (the agent pass
    needs the complete failure set)."""
    failures, new_files = [], []
    for row in rows:
        b = baseline.get(row["_key"])
        badge = rd._badge_of(row)
        row["badge"] = badge

        # absolute invariants (baseline or not)
        if row.get("bucket") == "ERROR":
            _fail(failures, "S0", "extract_error", row, None, row.get("reason"))
        if (row.get("pack_violations") or 0) > 0:
            _fail(failures, "S3", "pack_invariant", row, 0, row["pack_violations"],
                  {"samples": row.get("pack_violation_samples")})

        if b is None:
            new_files.append(row["_key"])
            if strict_new and badge in ("not_correct", "crashed"):
                _fail(failures, "S2", "new_file_red", row, None, badge)
            continue

        # S1 header
        if row.get("detected_format") != b.get("detected_format"):
            _fail(failures, "S1", "detected_format_changed", row,
                  b.get("detected_format"), row.get("detected_format"))
        if (row.get("unmapped_headers") or 0) > (b.get("unmapped_headers") or 0):
            _fail(failures, "S1", "unmapped_headers_up", row,
                  b.get("unmapped_headers"), row.get("unmapped_headers"),
                  {"headers": row.get("unmapped_header_names")})
        if (row.get("hard_empty_rate") or 0) > (b.get("hard_empty_rate") or 0) + 0.02:
            _fail(failures, "S1", "hard_required_emptier", row,
                  b.get("hard_empty_rate"), row.get("hard_empty_rate"))

        # S2 badge trajectory
        if _BADGE_RANK.get(badge, 9) > _BADGE_RANK.get(b.get("badge"), 9):
            _fail(failures, "S2", "badge_worsened", row, b.get("badge"), badge,
                  {"reason": row.get("reason_code")})

        # S3 product-name matching
        mm, bmm = row.get("master_match"), b.get("master_match")
        if mm is not None and bmm is not None and mm < bmm - 0.02:
            _fail(failures, "S3", "master_match_down", row, bmm, round(mm, 4))

        # S4 rows completeness
        rc, brc = row.get("row_count"), b.get("row_count")
        if rc is not None and brc is not None and rc < brc:
            _fail(failures, "S4", "row_count_down", row, brc, rc)
        lu, blu = row.get("line_unexplained"), b.get("line_unexplained")
        if lu is not None and blu is not None and lu > blu:
            _fail(failures, "S4", "line_unexplained_up", row, blu, lu,
                  {"sample": row.get("line_unexplained_sample")})
        if row.get("ledger_would_fire") and not b.get("ledger_would_fire"):
            _fail(failures, "S4", "new_would_fire", row, False, True,
                  {"sample": row.get("line_unexplained_sample")})

    stages = ("S0", "S1", "S2", "S3", "S4")
    status = {s: ("FAIL" if any(f["stage"] == s for f in failures) else "PASS")
              for s in stages}
    return failures, new_files, status


def baseline_entry(row):
    return {
        "route": row["route"], "badge": row.get("badge") or rd._badge_of(row),
        "bucket": row.get("bucket"), "reason_code": row.get("reason_code"),
        "detected_format": row.get("detected_format"),
        "unmapped_headers": row.get("unmapped_headers"),
        "hard_empty_rate": row.get("hard_empty_rate"),
        "master_match": row.get("master_match"),
        "pack_violations": row.get("pack_violations"),
        "row_count": row.get("row_count"),
        "line_unexplained": row.get("line_unexplained"),
        "ledger_would_fire": bool(row.get("ledger_would_fire")),
    }


# --------------------------------------------------------------------------- #
# S5 — meta battery (units + regression + mirror + cross-tree identity)
# --------------------------------------------------------------------------- #
_MIRRORED_SUITE_FILES = ("scripts/batch_extract.py", "scripts/batch_core.py",
                         "scripts/render_dashboard.py", "scripts/regression_test.py",
                         "scripts/run_full_suite.py",
                         "tests/test_triage.py", "tests/test_line_ledger.py",
                         "tests/test_pack_match.py")


def _sibling_tree():
    name = ROOT.name
    other = "Backends" if "Python-Service-UI" in name else "Python-Service-UI"
    cand = ROOT.parent / other
    return cand if cand.exists() else None


def run_s5(workers, log):
    checks = []

    def sub(label, cmd, cwd=ROOT):
        t0 = time.time()
        try:
            p = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                               timeout=7200)
            ok = p.returncode == 0
            tail = (p.stdout or p.stderr or "").strip().splitlines()[-1:] or [""]
        except Exception as exc:  # noqa: BLE001
            ok, tail = False, [f"{type(exc).__name__}: {exc}"]
        checks.append({"check": label, "ok": ok, "detail": tail[0],
                       "seconds": round(time.time() - t0, 1)})
        log(f"    {'PASS' if ok else 'FAIL'}  {label}  ({tail[0][:90]})")

    py = sys.executable
    if (ROOT / "tests" / "test_triage.py").exists():
        sub("pytest units", [py, "-m", "pytest", "tests", "-q",
                             "--ignore=tests/test_pack_match.py"])
    if (ROOT / "tests" / "test_pack_match.py").exists():
        sub("pack_match standalone", [py, "tests/test_pack_match.py"])
    if (ROOT / "scripts" / "regression_test.py").exists():
        sub("regression (all suites)", [py, "scripts/regression_test.py",
                                        "--workers", str(min(4, workers))])
    if (ROOT / "scripts" / "check_mirror_drift.py").exists():
        sub("engine mirror drift", [py, "scripts/check_mirror_drift.py"])
    sib = _sibling_tree()
    if sib is not None:
        bad = [f for f in _MIRRORED_SUITE_FILES
               if (ROOT / f).exists() and (sib / f).exists()
               and not filecmp.cmp(str(ROOT / f), str(sib / f), shallow=False)]
        missing = [f for f in _MIRRORED_SUITE_FILES if not (sib / f).exists()]
        ok = not bad and not missing
        checks.append({"check": "cross-tree suite identity", "ok": ok,
                       "detail": f"drift={bad} missing={missing}" if not ok else
                       f"{len(_MIRRORED_SUITE_FILES)} files identical in {sib.name}",
                       "seconds": 0})
        log(f"    {'PASS' if ok else 'FAIL'}  cross-tree suite identity"
            + (f"  ({bad + missing})" if not ok else ""))
    return checks


# --------------------------------------------------------------------------- #
# selftest — prove each gate fires on an injected regression
# --------------------------------------------------------------------------- #
def selftest(rows):
    """Seed an in-memory baseline from `rows`, mutate copies, assert the right
    gate fires for each mutation. Exit 0 only if all four fire."""
    import copy
    if len(rows) < 4:
        print("selftest needs >=4 analyzed files"); return 1
    base = {r["_key"]: baseline_entry(r) for r in rows}
    probes = []
    a, b_, c, d = (copy.deepcopy(rows[i]) for i in range(4))
    a["bucket"], a["extraction_ok"], a["reason_code"] = "RED", False, "SANITY_FAILED"
    probes.append(("S2", "badge_worsened", a))
    b_["row_count"] = max(0, (b_.get("row_count") or 1) - 3)
    probes.append(("S4", "row_count_down", b_))
    c["line_unexplained"] = (c.get("line_unexplained") or 0) + 7
    probes.append(("S4", "line_unexplained_up", c))
    d["pack_violations"], d["pack_violation_samples"] = 1, ["'X CREAM'->('X','CREAM')"]
    probes.append(("S3", "pack_invariant", d))
    ok = True
    for stage, kind, mutated in probes:
        fails, _, _ = run_gates([mutated], base)
        hit = any(f["stage"] == stage and f["kind"] == kind for f in fails)
        print(f"  {'PASS' if hit else 'FAIL'}  {stage}/{kind} fires on injected regression")
        ok = ok and hit
    clean_fails, _, _ = run_gates(rows[:4], base)
    quiet = not clean_fails
    print(f"  {'PASS' if quiet else 'FAIL'}  no false alarm on unmutated rows")
    return 0 if (ok and quiet) else 1


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="Ordered full test suite (see module docstring)")
    ap.add_argument("--folder", "--root", dest="folder", default=DEFAULT_ROOT)
    ap.add_argument("--workers", type=int,
                    default=min(18, max(1, (os.cpu_count() or 4) - 2)))
    ap.add_argument("--refresh", action="store_true", help="ignore extract cache")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only-under", default="", help="substring filter (smoke runs)")
    ap.add_argument("--baseline", default=str(BASELINE_PATH))
    ap.add_argument("--seed-baseline", action="store_true")
    ap.add_argument("--update-baseline", action="store_true",
                    help="rewrite the verdict baseline from this run (verified improvements only)")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--strict-new", action="store_true",
                    help="new (un-baselined) RED/crashed files fail the run")
    ap.add_argument("--allow-missing", action="store_true",
                    help="baselined files missing on disk don't fail S0")
    ap.add_argument("--skip-s5", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    root = Path(args.folder)
    if not root.exists():
        print(f"folder not found: {root}"); return 2
    runid = time.strftime("%Y%m%d_%H%M%S") + "_" + re.sub(r"[^A-Za-z0-9_-]+", "_", root.name)
    out_dir = ROOT / "_full_suite" / runid
    log = print

    log(f"[{ROOT.name}] full suite on {root}  (workers={args.workers})")
    jobs = discover(root, args.only_under, args.limit)
    if not jobs:
        print("no report files found"); return 2
    split = Counter(r for r, _ in jobs)
    log(f"  {len(jobs)} files  " + "  ".join(f"{r}:{n}" for r, n in sorted(split.items())))

    # ---- S0 extract ------------------------------------------------------- #
    t0 = time.time()
    results = be.extract_batch(jobs, workers=args.workers, refresh=args.refresh,
                               progress=True)
    err_jobs = [(r, p) for r, p in jobs
                if (results.get(str(p)) or {}).get("_extract_error")]
    if err_jobs:
        # real errors ARE cached; a worker-death (BrokenProcessPool) or timeout is
        # environmental — retry those serially with refresh so poison never sticks.
        log(f"  S0 retry: {len(err_jobs)} errored file(s), serial refresh")
        results.update(be.extract_batch(err_jobs, workers=1, refresh=True,
                                        progress=True))
    extract_errors = sum(1 for r, p in jobs
                         if (results.get(str(p)) or {}).get("_extract_error"))
    extract_seconds = round(time.time() - t0, 1)
    log(f"  S0 extract: {len(jobs)} files in {extract_seconds}s, {extract_errors} error(s)")
    del results  # workers reload from cache; don't hold 3k results in memory

    # ---- analysis pass (S1-S4 inputs, one build_quality per file) --------- #
    t0 = time.time()
    ajobs = [(route, p.parent.parent.name, p.name, str(p)) for route, p in jobs]
    rows = [None] * len(ajobs)
    if args.workers <= 1 or len(ajobs) <= 2:
        for i, j in enumerate(ajobs):
            rows[i] = analyze_one(j)
    else:
        from concurrent.futures import ProcessPoolExecutor, as_completed
        try:
            with ProcessPoolExecutor(max_workers=args.workers) as ex:
                futs = {ex.submit(analyze_one, j): i for i, j in enumerate(ajobs)}
                done = 0
                for fut in as_completed(futs):
                    rows[futs[fut]] = fut.result()
                    done += 1
                    if done % 200 == 0 or done == len(ajobs):
                        log(f"    analyzed {done}/{len(ajobs)}")
        except Exception as exc:  # spawn trouble -> serial, never lose the pass
            log(f"    parallel analysis failed ({exc}); serial fallback")
            for i, j in enumerate(ajobs):
                if rows[i] is None:
                    rows[i] = analyze_one(j)
    for row, (route, p) in zip(rows, jobs):
        row["_key"] = file_key(p)
    log(f"  analysis: {len(rows)} files in {round(time.time() - t0, 1)}s")

    if args.selftest:
        return selftest([r for r in rows if r.get("bucket") == "GREEN"][:8] or rows)

    # ---- baseline --------------------------------------------------------- #
    bpath = Path(args.baseline)
    baseline = {}
    if bpath.exists():
        baseline = json.loads(bpath.read_text(encoding="utf-8"))
    if args.seed_baseline and baseline and not args.force:
        print(f"baseline exists ({bpath}); use --force to overwrite"); return 2

    failures, new_files, gates = run_gates(rows, baseline, args.strict_new)

    # missing: baselined but no longer on disk (quarantined/moved) — surfaced,
    # gate-failing unless --allow-missing.
    seen = {r["_key"] for r in rows}
    missing = ([] if (args.only_under or args.limit) else
               sorted(k for k in baseline if k not in seen))
    if missing and not args.allow_missing:
        gates["S0"] = "FAIL"
    if extract_errors:
        gates["S0"] = "FAIL"

    # ---- dashboard (always rendered, S2 artifact) -------------------------- #
    buckets = Counter(r["bucket"] for r in rows)
    rec = {
        "batch": runid, "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_files": len(rows), "route_split": dict(split),
        "extract_seconds": extract_seconds, "extract_errors": extract_errors,
        "buckets": dict(buckets),
        "green_pct": round(100 * buckets.get("GREEN", 0) / len(rows)) if rows else 0,
        "triage_rows": rows, "clusters": _clusters(rows),
    }
    rd.render(rec, out_dir)
    log(f"  S2 dashboard: {out_dir / 'dashboard.html'}")

    # ---- S5 --------------------------------------------------------------- #
    s5 = []
    if not args.skip_s5:
        log("  S5 meta battery:")
        s5 = run_s5(args.workers, log)
        gates["S5"] = "PASS" if all(c["ok"] for c in s5) else "FAIL"

    # ---- seed / update ---------------------------------------------------- #
    if args.seed_baseline or args.update_baseline:
        if args.only_under or args.limit:
            merged = dict(baseline)  # partial run: merge, don't drop the rest
            merged.update({r["_key"]: baseline_entry(r) for r in rows})
        else:
            merged = {r["_key"]: baseline_entry(r) for r in rows}
        bpath.parent.mkdir(parents=True, exist_ok=True)
        bpath.write_text(json.dumps(merged, indent=1, ensure_ascii=False, sort_keys=True),
                         encoding="utf-8")
        log(f"  baseline {'seeded' if args.seed_baseline else 'updated'}: "
            f"{bpath} ({len(merged)} files)")

    # ---- failures.json + run.json ----------------------------------------- #
    clusters = {}
    for f in failures:
        k = (f["stage"], f["kind"], f["route"], f["layout"] or "?")
        c = clusters.setdefault(k, {"stage": k[0], "kind": k[1], "route": k[2],
                                    "layout": k[3], "count": 0, "files": []})
        c["count"] += 1
        if len(c["files"]) < 20:
            c["files"].append(f["file_key"])
    fail_doc = {
        "runid": runid, "tree": ROOT.name, "folder": str(root), "gates": gates,
        "failures": failures, "new_files": new_files[:500], "missing_files": missing,
        "s5": s5,
        "clusters": sorted(clusters.values(), key=lambda c: -c["count"]),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "failures.json").write_text(
        json.dumps(fail_doc, indent=1, ensure_ascii=False), encoding="utf-8")
    (out_dir / "triage_rows.json").write_text(
        json.dumps(rows, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    run_doc = {
        "runid": runid, "tree": ROOT.name, "folder": str(root),
        "workers": args.workers, "total_files": len(rows),
        "route_split": dict(split), "extract_seconds": extract_seconds,
        "extract_errors": extract_errors, "buckets": dict(buckets),
        "gates": gates, "failure_count": len(failures),
        "new_files": len(new_files), "missing_files": len(missing),
        "route_sigs": {r: be.route_code_sig(r) for r in sorted(split)},
    }
    (out_dir / "run.json").write_text(
        json.dumps(run_doc, indent=1, ensure_ascii=False), encoding="utf-8")
    (ROOT / "_full_suite" / "LATEST.txt").write_text(runid, encoding="utf-8")

    # ---- verdict ----------------------------------------------------------- #
    log("")
    for s in sorted(gates):
        log(f"  {gates[s]}  {s}")
    log(f"  failures={len(failures)}  new={len(new_files)}  missing={len(missing)}"
        f"  -> {out_dir / 'failures.json'}")
    all_pass = all(v == "PASS" for v in gates.values())
    log("ALL GREEN" if all_pass else "GATE FAILURES — see failures.json "
        "(run the agent pass per MASTER_FULL_SUITE_PROMPT.md)")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
