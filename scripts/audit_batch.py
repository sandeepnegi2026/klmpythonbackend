#!/usr/bin/env python3
"""
audit_batch.py — batch FORENSIC auditor (completeness + correctness, not just GREEN).

run_batch.py's dashboard proves the rows that WERE extracted reconcile (triage GREEN).
This tool proves nothing was DROPPED and every column is in the right field: it runs
the three independent oracles from EXTRACTION_AUDIT_RUNBOOK.md over every file in a
batch, folds in the triage verdict, runs the curated regression suites, checks the
engine mirror, and writes ONE self-contained audit_dashboard.html + AUDIT_SUMMARY.md.

The headline is TRUSTWORTHY vs NOT_TRUSTWORTHY, and the batch only PASSES the
acceptance gate when: 0 NOT_TRUSTWORTHY files AND regression 0-fail AND engine mirror
in sync — the Part 5 gate, automated.

  Oracle A (completeness, PDF): every candidate product line maps to an output row
                               (DELTA = candidate_lines - output_rows; MISSING = dropped)
  Oracle B (printed totals, PDF, advisory): printed GRAND/GROUP totals match column sums
  Oracle C (reconcile, stock): closing = opening + purchase + free - returns - sales

Extraction, triage, regression and mirror all reuse the SAME functions run_batch.py
uses (shared extract cache, core.quality, batch_core, render_dashboard) so verdicts
match the standalone tools.

Usage:
  .venv/Scripts/python.exe scripts/audit_batch.py --suite 15july_fixes_stock_pdf
  .venv/Scripts/python.exe scripts/audit_batch.py --folder "D:/Data/CG" --route stock_pdf
  .venv/Scripts/python.exe scripts/audit_batch.py --folder "D:/Drop"          # auto-route
  .venv/Scripts/python.exe scripts/audit_batch.py --folder "D:/CG" --route stock_pdf \
        --skip-regression --skip-mirror --workers 6 --out ./_audit/CG
"""
from __future__ import annotations

import argparse
import os
import io
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pdfplumber  # noqa: E402

# The dashboard/summary emoji (✅/❌/🎉) are written to utf-8 files, but the console
# on Windows defaults to cp1252 and would crash on them — wrap stdout like detect_diff.
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import batch_extract as be  # noqa: E402
import batch_core as bc  # noqa: E402
import render_dashboard as rd  # noqa: E402
from run_batch import route_for_path  # noqa: E402
from audit_one import (  # noqa: E402
    candidate_data_lines,
    printed_totals,
    _norm,
    _line_matches_a_row,
)

PROJECTS = ROOT.parent
AUDIT_COLOR = {"TRUSTWORTHY": "#d7f5dd", "SUSPECT": "#fff3cd",
               "NOT_TRUSTWORTHY": "#f8d7da", "ERROR": "#e2e3e5"}
AUDIT_ORDER = {"NOT_TRUSTWORTHY": 0, "ERROR": 1, "SUSPECT": 2, "TRUSTWORTHY": 3}
QTY_FIELDS = ("opening_stock", "purchase_stock", "sales_qty", "closing_stock")
VAL_FIELDS = ("sales_value", "closing_stock_value")
RECON = ("opening_stock", "purchase_stock", "purchase_free", "purchase_return",
         "sales_qty", "sales_free", "sales_return", "closing_stock")


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


# --------------------------------------------------------------------------- #
# discovery
# --------------------------------------------------------------------------- #
def discover(args):
    if args.suite:
        yield from _iter_suite(args.suite)
        return
    folder = Path(args.folder)
    if not folder.exists():
        raise SystemExit(f"Folder not found: {folder}")
    exts_all = be.PDF_EXTS | be.XLSX_EXTS
    for f in sorted(folder.rglob("*")):
        if not (f.is_file() and f.suffix.lower() in exts_all):
            continue
        low = str(f).lower()
        if any(x in low for x in ("need reviews", "_wrong_format", "_misfiled")):
            continue                            # quarantine/relocated buckets, never in a run
        route = args.route or route_for_path(f)
        if args.route and f.suffix.lower() not in be.exts_for_route(route):
            continue                            # --route pins the extension family
        yield route, f


def _iter_suite(names):
    manifest = json.loads((ROOT / "tests" / "regression_manifest.json").read_text(encoding="utf-8"))
    reports_root = (ROOT / manifest.get("reports_root", "../..")).resolve()
    suites = manifest["suites"]
    for name in names:
        cfg = suites.get(name)
        if not cfg:
            print(f"  WARN: unknown suite '{name}' (known: {', '.join(sorted(suites))})")
            continue
        route = cfg["route"]
        exts = be.exts_for_route(route)
        for path in _suite_files(cfg, reports_root, exts):
            yield route, path


def _suite_files(cfg, reports_root, exts):
    out = []
    if cfg.get("files"):
        for rel in cfg["files"]:
            p = (reports_root / rel).resolve()
            if p.is_file() and p.suffix.lower() in exts:
                out.append(p)
        return out
    if "glob" in cfg:
        head = cfg["glob"].split("*.", 1)[0].rstrip("/")
        base = reports_root / head
        if base.exists():
            out = [p for p in sorted(base.glob("*")) if p.is_file() and p.suffix.lower() in exts]
    return out


# --------------------------------------------------------------------------- #
# per-file oracle audit
# --------------------------------------------------------------------------- #
def _raw_text(path, data):
    """PDF -> concatenated page text; xlsx -> None (line-census / printed-total
    oracles are PDF-only, so they report NA for spreadsheets)."""
    if not str(path).lower().endswith(".pdf"):
        return None
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            return "\n".join((pg.extract_text() or "") for pg in pdf.pages)
    except Exception:
        return None


def audit_file(route, path, result):
    tri = bc.triage_row(route, path.parent.name, path.name, str(path), result)
    rows = result.get("rows") or []
    rec = {
        "file_name": path.name, "path": str(path), "route": route, "layout": tri.get("layout"),
        "triage_bucket": tri.get("bucket"), "reason_code": tri.get("reason_code"),
        "row_count": len(rows), "delta": None, "missing": 0, "missing_sample": "",
        "recon_bad": 0, "recon_checked": 0, "b_matched": 0, "b_total": 0,
        "oracleA": "NA", "oracleB": "NA", "oracleC": "NA", "note": "", "audit_reason": "clean",
    }
    if result.get("_extract_error"):
        rec.update(verdict="ERROR", audit_reason="extraction crashed", note=str(result["_extract_error"]))
        return rec

    try:
        data = path.read_bytes()
    except OSError as exc:
        rec.update(verdict="ERROR", audit_reason="file unreadable", note=f"unreadable: {exc}")
        return rec
    raw = _raw_text(path, data)

    # -- Oracle A: completeness (STOCK PDFs only) ---------------------------
    # The line census assumes ~one product per line (stock statements). Party
    # product-wise PDFs interleave party / address / town / invoice sub-lines,
    # so candidate_data_lines massively OVER-counts and DELTA is meaningless
    # there. Scope Oracle A to stock; party completeness leans on Oracle B
    # (printed totals) + triage instead.
    if raw is not None and route.startswith("stock"):
        cands = candidate_data_lines(raw)
        norm_names = [_norm(str(r.get("product_name", ""))) for r in rows]
        missing = [s for s in cands if not _line_matches_a_row(s, norm_names)]
        rec["delta"] = len(cands) - len(rows)
        rec["missing"] = len(missing)
        rec["missing_sample"] = "; ".join(m[:70] for m in missing[:3])
        rec["oracleA"] = "FAIL" if missing else "PASS"

    # -- Oracle B: printed totals vs column sums (PDF only, advisory) --------
    if raw is not None:
        sums = [s for s in (sum(_f(r.get(f)) for r in rows) for f in QTY_FIELDS + VAL_FIELDS) if s]
        printed = {round(n, 2) for _ln, nums in printed_totals(raw) for n in nums if n >= 1}
        rec["b_total"] = len(printed)
        rec["b_matched"] = sum(1 for p in printed
                               if any(abs(p - s) <= 0.02 * max(abs(s), 1) for s in sums))
        if rec["b_total"]:
            rec["oracleB"] = "PASS" if rec["b_matched"] >= max(1, round(0.5 * rec["b_total"])) else "GAP"

    # -- Oracle C: reconcile identity (stock only) --------------------------
    # Independent recompute of the raw identity (does NOT trust the parser's
    # exp_damage/shortage adjustment columns, unlike triage's effective_sanity) —
    # so this is stricter on purpose. Hard-FAIL only on a SYSTEMIC break (a
    # column-swap fails most rows); a couple of rounding/adjustment rows -> PASS.
    if route.startswith("stock"):
        chk = 0
        for r in rows:
            v = {k: _f(r.get(k)) for k in RECON}
            if all(x == 0 for x in v.values()):
                continue
            chk += 1
            base = (v["opening_stock"] + v["purchase_stock"] + v["purchase_free"]
                    - v["purchase_return"] - v["sales_qty"] - v["sales_free"] + v["sales_return"])
            if abs(base - v["closing_stock"]) > 0.05 * max(abs(v["closing_stock"]), 1):
                rec["recon_bad"] += 1
        rec["recon_checked"] = chk
        if chk:
            rec["oracleC"] = "FAIL" if rec["recon_bad"] >= max(2, 0.10 * chk) else "PASS"

    # -- verdict ------------------------------------------------------------
    # Oracle C (reconcile) is a RELIABLE hard signal -> reconcile FAIL is a
    # confirmed break. Oracle A (line census) is a documented HEURISTIC screen
    # (1-2 false positives from odd hyphenation are normal), so a small DELTA is
    # only SUSPECT (goes to the eyeball/Prompt-1 queue). An egregious drop —
    # missing >= half the output rows AND >= 10 lines — is the SUBRAHMANYA-class
    # mass-drop the whole runbook exists to catch, so it hard-fails too.
    _delta = rec["delta"] or 0
    mass_drop = (rec["oracleA"] == "FAIL" and _delta >= 10
                 and _delta >= 0.5 * max(rec["row_count"], 1))
    hard = rec["oracleC"] == "FAIL" or mass_drop
    soft = (rec["oracleA"] == "FAIL" or rec["oracleB"] == "GAP"
            or rec["triage_bucket"] in ("AMBER", "RED"))
    rec["verdict"] = "NOT_TRUSTWORTHY" if hard else ("SUSPECT" if soft else "TRUSTWORTHY")

    # audit_reason — the AUDIT's own diagnosis (not triage's reason_code), most
    # severe first, so clusters read "reconcile fails" not the misleading "CLEAN".
    if rec["oracleC"] == "FAIL":
        rec["audit_reason"] = f"reconcile fails (Oracle C: {rec['recon_bad']}/{rec['recon_checked']} rows)"
    elif mass_drop:
        rec["audit_reason"] = f"mass row-drop (Oracle A: DELTA {rec['delta']} vs {rec['row_count']} rows)"
    elif rec["oracleA"] == "FAIL":
        # `missing` (name-unmatched lines) is the NOISY per-line screen; `delta`
        # (net rows vs candidate lines) is the RELIABLE drop signal. A big missing
        # with a small delta = matcher noise, not a real drop -> say both so the
        # SUSPECT verdict reads honestly and isn't mistaken for a confirmed drop.
        rec["audit_reason"] = (f"Oracle A screen: {rec['missing']} name-unmatched line(s), "
                               f"net DELTA {rec['delta']} vs {rec['row_count']} rows — eyeball (Prompt 1)")
    elif rec["oracleB"] == "GAP":
        rec["audit_reason"] = f"printed total gap (Oracle B: {rec['b_matched']}/{rec['b_total']} matched)"
    elif rec["triage_bucket"] in ("AMBER", "RED"):
        rec["audit_reason"] = f"triage {rec['triage_bucket']}: {rec['reason_code']}"
    return rec


def cluster(rows):
    """Group everything that is NOT TRUSTWORTHY by (route, layout) — the work-list."""
    groups: dict[tuple, dict] = {}
    for r in rows:
        if r["verdict"] == "TRUSTWORTHY":
            continue
        key = (r["route"], r.get("layout"))
        g = groups.setdefault(key, {"count": 0, "verdicts": Counter(),
                                    "example": r["file_name"], "reason": r.get("audit_reason"),
                                    "reasons": Counter()})
        g["count"] += 1
        g["verdicts"][r["verdict"]] += 1
        g["reasons"][r.get("audit_reason")] += 1
    for g in groups.values():
        g["reason"] = g["reasons"].most_common(1)[0][0]
    # NOT_TRUSTWORTHY clusters first, then by size — the true work-list order.
    def _rank(kv):
        v = kv[1]["verdicts"]
        return (0 if v.get("NOT_TRUSTWORTHY") or v.get("ERROR") else 1, -kv[1]["count"])
    return sorted(groups.items(), key=_rank)


# --------------------------------------------------------------------------- #
# regression + mirror (same logic as run_batch phases 7 & 9)
# --------------------------------------------------------------------------- #
def run_regression(workers, only=None, reg_all=False):
    manifest = json.loads((ROOT / "tests" / "regression_manifest.json").read_text(encoding="utf-8"))
    reports_root = (ROOT / manifest.get("reports_root", "../..")).resolve()
    suites = manifest["suites"]
    baselines = ROOT / "tests" / "baselines"
    chosen = {n: c for n, c in suites.items()
              if ((n in only) if only else ("files" in c or reg_all))}
    results = []
    for name, cfg in chosen.items():
        route = cfg["route"]
        files = _suite_files(cfg, reports_root, be.exts_for_route(route))
        if not files:
            continue
        res = be.extract_batch([(route, p) for p in files], workers=workers, progress=False)
        p = f = miss = 0
        moved = Counter()
        for path in files:
            actual = bc.regression_metrics(route, path.name, res.get(str(path), {}))
            bpath = baselines / name / f"{path.name.replace('/', '_').replace(chr(92), '_')}.json"
            if not bpath.exists():
                miss += 1
                continue
            expected = json.loads(bpath.read_text(encoding="utf-8"))
            diffs = [k for k in set(expected) | set(actual)
                     if k not in ("file", "route") and expected.get(k) != actual.get(k)]
            if diffs:
                f += 1
                for k in diffs:
                    moved[k] += 1
            else:
                p += 1
        results.append({"suite": name, "passed": p, "failed": f, "missing": miss,
                        "fields_moved": dict(moved)})
    return results


def _dirs_equal(a: Path, b: Path) -> bool:
    import filecmp
    if not a.exists() or not b.exists():
        return False
    af = {p.relative_to(a).as_posix() for p in a.rglob("*.py")}
    bf = {p.relative_to(b).as_posix() for p in b.rglob("*.py")}
    if af != bf:
        return False
    return all(filecmp.cmp(a / rel, b / rel, shallow=False) for rel in af)


def check_mirror():
    import filecmp
    status = {}
    for sub in ("core", "extractors"):
        status[sub] = _dirs_equal(PROJECTS / "Backends" / sub, PROJECTS / "Python-Service-UI" / sub)
    pm_a = PROJECTS / "Backends" / "data" / "product_master.json"
    pm_b = PROJECTS / "Python-Service-UI" / "data" / "product_master.json"
    status["product_master.json"] = (pm_a.exists() and pm_b.exists()
                                     and filecmp.cmp(pm_a, pm_b, shallow=False))
    return status


# --------------------------------------------------------------------------- #
# render — audit_dashboard.html + AUDIT_SUMMARY.md (reuses render_dashboard style)
# --------------------------------------------------------------------------- #
def _gate_pass(rec):
    nt = rec["buckets"].get("NOT_TRUSTWORTHY", 0) + rec["buckets"].get("ERROR", 0)
    rf = sum(r["failed"] for r in rec.get("regression", []))
    mirror = rec.get("mirror")
    mirror_ok = all(mirror.values()) if mirror else True
    return nt == 0 and rf == 0 and mirror_ok


def render_summary(rec) -> str:
    b = rec["buckets"]
    total = rec["total_files"]
    reg = rec.get("regression", [])
    rp, rf = sum(r["passed"] for r in reg), sum(r["failed"] for r in reg)
    mirror = rec.get("mirror")
    L = [f"# Audit summary — {rec['batch']}  ({rec['generated']})", "",
         f"**{_headline_text(rec)[1]}**", "",
         f"- Files: **{total}**  ·  TRUSTWORTHY {b.get('TRUSTWORTHY', 0)} "
         f"({rd._pct(b.get('TRUSTWORTHY', 0), total)}%) ·  SUSPECT {b.get('SUSPECT', 0)} ·  "
         f"NOT_TRUSTWORTHY {b.get('NOT_TRUSTWORTHY', 0)} ·  ERROR {b.get('ERROR', 0)}",
         f"- Triage (kept-row reconcile only): GREEN {rec['triage_buckets'].get('GREEN', 0)} · "
         f"AMBER {rec['triage_buckets'].get('AMBER', 0)} · RED {rec['triage_buckets'].get('RED', 0)}",
         f"- Dropped-row failures (Oracle A): {sum(1 for r in rec['rows'] if r['oracleA'] == 'FAIL')} · "
         f"reconcile failures (Oracle C): {sum(1 for r in rec['rows'] if r['oracleC'] == 'FAIL')}",
         f"- Regression: {rp} pass / {rf} fail across {len(reg)} curated suite(s)",
         f"- Engine mirror: {'IN SYNC' if (mirror and all(mirror.values())) else ('DRIFT' if mirror else 'skipped')}",
         "", "## FIX THESE FIRST (not-trustworthy clusters, most files first)"]
    for i, ((route, layout), g) in enumerate(rec["clusters"][:8], 1):
        vd = ", ".join(f"{k}:{n}" for k, n in g["verdicts"].most_common())
        L.append(f"{i}. {route}/`{layout}` — {g['count']} file(s) [{vd}] · {g['reason']} · e.g. {g['example']}")
    if not rec["clusters"]:
        L.append("- Nothing flagged — every file is TRUSTWORTHY. 🎉")
    L += ["", "Full dashboard: audit_dashboard.html (in this folder)"]
    return "\n".join(L) + "\n"


def _headline_text(rec):
    """(css_class, message) — three honest states, not a binary."""
    suspect = rec["buckets"].get("SUSPECT", 0)
    if not rec["gate_pass"]:
        return "bad", "❌ NOT APPROVED — confirmed breaks / regression fail / mirror drift (see gate)"
    if suspect:
        return "ok", (f"✅ NO CONFIRMED BREAKS — but {suspect} file(s) need an eyeball / "
                      "single-file deep audit (Prompt 1) before auto-posting")
    return "ok", "✅ APPROVED — every file is TRUSTWORTHY"


def _banner(rec):
    cls, txt = _headline_text(rec)
    b, total = rec["buckets"], rec["total_files"]
    pills = " ".join(
        f"<span class='pill' style='background:{AUDIT_COLOR[k]}'>{k.replace('_', ' ')} "
        f"{b.get(k, 0)} ({rd._pct(b.get(k, 0), total)}%)</span>"
        for k in ("TRUSTWORTHY", "SUSPECT", "NOT_TRUSTWORTHY", "ERROR") if b.get(k))
    tb = rec["triage_buckets"]
    tri = " ".join(f"<span class='pill' style='background:{rd.BUCKET_COLOR[k]}'>{k} {tb.get(k, 0)}</span>"
                   for k in ("GREEN", "AMBER", "RED") if tb.get(k))
    return (f"<div class='head'><div class='bigrow'><div class='big'>{total} files</div>"
            f"<div>{pills}</div></div>"
            f"<div class='note'><span class='{cls}' style='font-size:16px'>{txt}</span></div>"
            f"<div class='note'>Triage (kept-row reconcile only, for contrast): {tri}</div></div>")


def _gates(rec):
    reg = rec.get("regression", [])
    rp, rf = sum(r["passed"] for r in reg), sum(r["failed"] for r in reg)
    mirror = rec.get("mirror")
    out = ["<h2>Acceptance gate (Part 5)</h2>"]
    nt = rec["buckets"].get("NOT_TRUSTWORTHY", 0) + rec["buckets"].get("ERROR", 0)
    out.append(f"<div class='gate'>Oracle A/C completeness+reconcile: "
               f"<span class='{'ok' if nt == 0 else 'bad'}'>{nt} not-trustworthy file(s)</span></div>")
    if reg:
        out.append(f"<div class='gate'>Regression: <span class='{'ok' if rf == 0 else 'bad'}'>"
                   f"{rp} pass / {rf} fail</span> across {len(reg)} curated suite(s)</div>")
    else:
        out.append("<div class='gate'>Regression: <span class='muted'>skipped (--skip-regression)</span></div>")
    if mirror:
        ok = all(mirror.values())
        detail = "  ".join(f"{k}:{'ok' if v else 'DIFF'}" for k, v in mirror.items())
        out.append(f"<div class='gate'>Engine mirror: <span class='{'ok' if ok else 'bad'}'>"
                   f"{'IN SYNC' if ok else 'DRIFT — reconcile before deploy'}</span> "
                   f"<span class='muted mono'>{rd._esc(detail)}</span></div>")
    else:
        out.append("<div class='gate'>Engine mirror: <span class='muted'>skipped (--skip-mirror)</span></div>")
    return "".join(out)


def _clusters_html(rec):
    total = rec["total_files"] or 1
    out = ["<h2>FIX THESE FIRST — not-trustworthy clusters (fix one layout, every file in it clears)</h2>",
           "<table><tr><th>#</th><th>route</th><th>layout</th><th>files</th><th>%</th>"
           "<th>verdicts</th><th>top reason</th><th>example</th></tr>"]
    for i, ((route, layout), g) in enumerate(rec["clusters"], 1):
        vd = ", ".join(f"{k.replace('_', ' ')}:{n}" for k, n in g["verdicts"].most_common())
        out.append(f"<tr><td>{i}</td><td>{rd._esc(route)}</td><td class='mono'>{rd._esc(layout)}</td>"
                   f"<td>{g['count']}</td><td>{rd._pct(g['count'], total)}%</td><td>{rd._esc(vd)}</td>"
                   f"<td class='rc'>{rd._esc(g['reason'])}</td><td class='mono'>{rd._esc(g['example'])}</td></tr>")
    if not rec["clusters"]:
        out.append("<tr><td colspan='8' class='ok'>Nothing flagged — every file is TRUSTWORTHY. 🎉</td></tr>")
    out.append("</table>")
    return "".join(out)


def _dropped_html(rec):
    bad = [r for r in rec["rows"] if r["oracleA"] == "FAIL" or r["oracleC"] == "FAIL"]
    if not bad:
        return "<h2>Completeness &amp; reconcile</h2><p class='ok'>No dropped rows and no reconcile failures. 🎉</p>"
    rows = ["<h2>Completeness &amp; reconcile — review queue (Oracle A / C)</h2>",
            "<p class='muted'>Oracle A (line census) is a HEURISTIC screen: a positive DELTA means "
            "candidate product lines outnumber output rows — a likely drop, but continuation lines / "
            "repeated headers / subtotals can inflate it. Ranked by size; confirm the top ones with the "
            "single-file deep audit (Prompt 1). Oracle C (reconcile) is reliable — a FAIL is a real break.</p>",
            "<table><tr><th>file</th><th>route</th><th>layout</th><th>rows</th><th>DELTA</th>"
            "<th>missing</th><th>recon bad</th><th>sample dropped line</th></tr>"]
    for r in sorted(bad, key=lambda x: -(x["missing"] + x["recon_bad"])):
        rows.append(f"<tr style='background:{AUDIT_COLOR['NOT_TRUSTWORTHY']}'>"
                    f"<td class='mono'>{rd._file_link(r.get('path'), r['file_name'])}</td><td>{rd._esc(r['route'])}</td>"
                    f"<td class='mono'>{rd._esc(r['layout'])}</td><td>{r['row_count']}</td>"
                    f"<td>{rd._esc(r['delta'])}</td><td>{r['missing']}</td><td>{r['recon_bad']}</td>"
                    f"<td class='mono'>{rd._esc(r['missing_sample'])}</td></tr>")
    rows.append("</table>")
    return "".join(rows)


def _panels(rec):
    out = []
    # regression
    reg = rec.get("regression", [])
    if reg:
        rrows = "".join(
            f"<tr><td class='mono'>{rd._esc(r['suite'])}</td><td>{r['passed']}</td><td>{r['failed']}</td>"
            f"<td class='mono'>{rd._esc(', '.join(f'{k}:{v}' for k, v in r.get('fields_moved', {}).items()))}</td></tr>"
            for r in reg)
        out.append("<details><summary>Regression (curated suites)</summary>"
                   "<table><tr><th>suite</th><th>pass</th><th>fail</th><th>fields moved</th></tr>"
                   + rrows + "</table></details>")
    # all files with oracle columns
    frows = []
    for r in sorted(rec["rows"], key=lambda x: (AUDIT_ORDER.get(x["verdict"], 9),
                                                x["route"], x["file_name"])):
        frows.append(
            f"<tr style='background:{AUDIT_COLOR.get(r['verdict'], '#fff')}'>"
            f"<td class='mono'>{rd._file_link(r.get('path'), r['file_name'])}</td><td>{rd._esc(r['route'])}</td>"
            f"<td>{rd._esc(r['verdict'].replace('_', ' '))}</td>"
            f"<td>{rd._esc(r['triage_bucket'])}</td><td>{r['row_count']}</td>"
            f"<td>{rd._esc(r['delta'])}</td>"
            f"<td>{rd._esc(r['oracleA'])}</td><td>{rd._esc(r['oracleB'])} "
            f"({r['b_matched']}/{r['b_total']})</td><td>{rd._esc(r['oracleC'])}</td>"
            f"<td class='rc'>{rd._esc(r['audit_reason'])}</td></tr>")
    out.append("<details open><summary>All files ({})</summary><table>"
               "<tr><th>file</th><th>route</th><th>audit verdict</th><th>triage</th><th>rows</th>"
               "<th>DELTA</th><th>A</th><th>B (matched)</th><th>C</th><th class='rc'>audit reason</th></tr>"
               "{}</table></details>".format(len(rec["rows"]), "".join(frows)))
    return "".join(out)


def render_html(rec) -> str:
    return (
        "<!doctype html><meta charset='utf-8'><title>Audit dashboard — "
        + rd._esc(rec["batch"]) + "</title><style>" + rd._CSS + "</style><div class='wrap'>"
        + f"<h1>Forensic audit — {rd._esc(rec['batch'])}</h1>"
        + f"<p class='sub'>generated {rd._esc(rec['generated'])} · extract {rec.get('extract_seconds', '?')}s · "
        + f"{rec.get('extract_errors', 0)} unreadable · beyond-GREEN oracles A/B/C</p>"
        + _banner(rec) + _gates(rec) + _clusters_html(rec) + _dropped_html(rec)
        + "<h2>Details</h2>" + _panels(rec)
        + "</div>")


def render(rec, out_dir: Path):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "AUDIT_SUMMARY.md").write_text(render_summary(rec), encoding="utf-8")
    (out_dir / "audit_dashboard.html").write_text(render_html(rec), encoding="utf-8")
    slim = {k: v for k, v in rec.items() if k != "rows"}
    (out_dir / "audit_run.json").write_text(json.dumps(slim, indent=2, ensure_ascii=False, default=str),
                                            encoding="utf-8")
    # full per-file rows (plain dicts) so --render-only can re-render with NO oracle pass
    (out_dir / "audit_rows.json").write_text(
        json.dumps(rec.get("rows", []), ensure_ascii=False, default=str), encoding="utf-8")


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description="Batch forensic auditor (oracles + triage + regression + mirror -> dashboard)")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--folder", help="Drop folder (recurses; auto-routes unless --route given)")
    src.add_argument("--suite", action="append", help="Curated manifest suite(s), e.g. 15july_fixes_stock_pdf")
    ap.add_argument("--route", choices=sorted(be.ROUTES), help="Pin the route for --folder")
    ap.add_argument("--out", default=None, help="Output dir (default _audit/<name>)")
    ap.add_argument("--workers", type=int, default=min(16, max(1, (os.cpu_count() or 4) - 2)),
                    help="Parallel extraction workers (default: auto = min(16, cores-2))")
    ap.add_argument("--refresh", action="store_true", help="Ignore the extract cache")
    ap.add_argument("--skip-regression", action="store_true")
    ap.add_argument("--skip-mirror", action="store_true")
    ap.add_argument("--reg-suites", nargs="+", help="Regression: only these suites")
    ap.add_argument("--reg-all", action="store_true", help="Regression: include slow glob suites too")
    ap.add_argument("--render-only", action="store_true",
                    help="Re-render audit_dashboard.html/AUDIT_SUMMARY.md from a prior run's "
                         "audit_rows.json — NO oracle pass (use after a render/format change)")
    args = ap.parse_args()

    if args.render_only:
        name = "_".join(args.suite) if args.suite else Path(args.folder).name
        out_dir = Path(args.out) if args.out else (ROOT / "_audit" / name)
        rows_p, run_p = out_dir / "audit_rows.json", out_dir / "audit_run.json"
        if not rows_p.exists():
            raise SystemExit(f"--render-only needs {rows_p} from a prior audit run.")
        rows = json.loads(rows_p.read_text(encoding="utf-8"))
        prev = json.loads(run_p.read_text(encoding="utf-8")) if run_p.exists() else {}
        rec = {
            "batch": name, "generated": prev.get("generated", time.strftime("%Y-%m-%d %H:%M:%S")),
            "total_files": len(rows), "extract_seconds": prev.get("extract_seconds", "?"),
            "extract_errors": prev.get("extract_errors", 0), "rows": rows,
            "buckets": dict(Counter(r["verdict"] for r in rows)),
            "triage_buckets": dict(Counter(r["triage_bucket"] for r in rows)),
            "clusters": cluster(rows), "regression": prev.get("regression", []),
            "mirror": prev.get("mirror"),
        }
        rec["gate_pass"] = _gate_pass(rec)
        render(rec, out_dir)
        print(f"Re-rendered from saved rows -> {out_dir / 'audit_dashboard.html'}")
        return 0

    jobs = list(discover(args))
    if not jobs:
        print("No matching files found.")
        return 2
    name = "_".join(args.suite) if args.suite else Path(args.folder).name
    out_dir = Path(args.out) if args.out else (ROOT / "_audit" / name)

    split = Counter(route for route, _ in jobs)
    print(f"Auditing {len(jobs)} file(s)  " + "  ".join(f"{r}:{n}" for r, n in sorted(split.items()))
          + f"  ({args.workers} worker(s))\n")

    t0 = time.time()
    results = be.extract_batch(jobs, workers=args.workers, refresh=args.refresh, progress=True)
    extract_seconds = round(time.time() - t0, 1)
    extract_errors = sum(1 for r in results.values() if r.get("_extract_error"))

    rows = []
    for route, path in jobs:
        rec = audit_file(route, path, results.get(str(path), {}))
        rows.append(rec)
        print(f"  {rec['verdict']:16} A:{rec['oracleA']:4} C:{rec['oracleC']:4} "
              f"DELTA:{str(rec['delta']):>4} {rec['file_name']}")

    buckets = Counter(r["verdict"] for r in rows)
    triage_buckets = Counter(r["triage_bucket"] for r in rows)
    clusters = cluster(rows)

    regression = [] if args.skip_regression else run_regression(
        args.workers, only=args.reg_suites, reg_all=args.reg_all)
    mirror = None if args.skip_mirror else check_mirror()

    rec = {
        "batch": name, "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_files": len(rows), "extract_seconds": extract_seconds,
        "extract_errors": extract_errors, "rows": rows, "buckets": dict(buckets),
        "triage_buckets": dict(triage_buckets), "clusters": clusters,
        "regression": regression, "mirror": mirror,
    }
    rec["gate_pass"] = _gate_pass(rec)
    render(rec, out_dir)

    print("\n" + "=" * 64)
    for k in ("TRUSTWORTHY", "SUSPECT", "NOT_TRUSTWORTHY", "ERROR"):
        if buckets.get(k):
            print(f"  {k:16}: {buckets[k]}")
    rf = sum(r["failed"] for r in regression)
    print(f"\n  regression: {sum(r['passed'] for r in regression)} pass / {rf} fail"
          + ("" if not args.skip_regression else "  (skipped)"))
    print(f"  mirror    : {'IN SYNC' if (mirror and all(mirror.values())) else ('DRIFT' if mirror else 'skipped')}")
    print(f"\n  {'✅ APPROVED' if rec['gate_pass'] else '❌ NOT APPROVED'} — see gate above")
    print(f"  dashboard : {out_dir / 'audit_dashboard.html'}")
    print(f"  summary   : {out_dir / 'AUDIT_SUMMARY.md'}")
    return 0 if rec["gate_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
