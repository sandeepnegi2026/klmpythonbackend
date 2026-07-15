#!/usr/bin/env python3
"""
run_batch.py — ONE command that processes a whole vendor batch end-to-end.

Replaces the copy-paste of three manual runbooks (NEW_BATCH_RUNBOOK Step 1 / Step 2 /
CATALOG_ENRICHMENT_RUNBOOK Step 3). It extracts every file ONCE (shared cache) and
fans that single extraction out to every phase, then writes ONE dashboard.

    python scripts/run_batch.py --batch 26_june --workers 6
    python scripts/run_batch.py --folder "D:/Devs/Reports/Data/New Data/10 July" --register

Phases (AUTO run unattended; GATE needs an explicit opt-in flag — nothing that
changes data/code happens without you):

  1 inspect          AUTO   count files, route split
  2 extract-once     AUTO   fill the shared _extract_cache (parallel)
  3 triage           AUTO   bucket GREEN/AMBER/RED + cluster work-list
  4 relocate         AUTO   list misfiled (party<->stock);  move = --apply-relocate
  5 headers          AUTO   list unmapped header candidates (editorial -> stays a candidate)
  6 products         AUTO   list product-synonym candidates;  write = --apply-products
  7 regression       AUTO   compare curated suites to baselines;  refresh = --update-baselines
  8 quarantine       AUTO   list scanned/corrupt;  move = --apply-quarantine
  9 mirror-check     AUTO   Backends vs Python-Service-UI engine + product_master parity
 10 dashboard        AUTO   write dashboard.html + SUMMARY.md

Use --only / --skip / --from to run a subset. The gated writes shell out to the
existing, battle-tested CLIs so their behaviour is identical to running them by hand.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import batch_extract as be
import batch_core as bc
import render_dashboard as rd

PY = sys.executable
PROJECTS = ROOT.parent
DATA_ROOT_DEFAULT = PROJECTS.parent / "Data"

ALL_PHASES = ["inspect", "extract", "triage", "relocate", "headers",
              "products", "regression", "quarantine", "mirror", "dashboard"]


def _triage_one_cached(job):
    """Process-pool worker: reload one file's cached extraction and triage it.

    Reloads via batch_extract.get (a fast disk read — every file is already in the
    shared cache after phase_extract) instead of pickling big result dicts through
    the pool. Module-level + run_batch's __main__ guard => safe under Windows spawn.
    """
    route, vendor, file_name, path_str = job
    try:
        result = be.get(route, path_str)
    except Exception as exc:  # defensive: never let one bad file kill the phase
        result = {"_extract_error": f"{type(exc).__name__}: {exc}"}
    return bc.triage_row(route, vendor, file_name, path_str, result)


# --------------------------------------------------------------------------- #
# routing & discovery
# --------------------------------------------------------------------------- #
def route_for_path(path: Path) -> str:
    """party/stock x pdf/xlsx from folder+filename hint (mirrors the harvest tools)."""
    ext = path.suffix.lower()
    is_xlsx = ext in (".xls", ".xlsx", ".xlsm")
    # The vendor-drop convention (mirrors the app's upload slots) is an explicit
    # "Party report" / "Stock report" subfolder — that beats any filename hint.
    for anc in path.parents:
        n = anc.name.strip().lower()
        # endswith: vendors annotate the slot folders ("ERROR Party report",
        # "RED — SANITY_FAILED STOCK FILE") — the slot name is always the suffix.
        if n.endswith(("party report", "party reports", "party file", "party files")):
            return "party_xlsx" if is_xlsx else "party_pdf"
        if n.endswith(("stock report", "stock reports", "stock file", "stock files")):
            return "stock_xlsx" if is_xlsx else "stock_pdf"
    s = str(path).lower()
    party_hint = ("party wise" in s) or ("party_wise" in s) or ("party_product" in s)
    stock_hint = ("sales and stock" in s) or ("stock and sales" in s) or ("stock_sales" in s)
    is_party = party_hint and not stock_hint
    if is_party:
        return "party_xlsx" if is_xlsx else "party_pdf"
    return "stock_xlsx" if is_xlsx else "stock_pdf"


def iter_batch(name: str, batches_path: Path):
    cfg = json.loads(batches_path.read_text(encoding="utf-8"))
    data_root = (ROOT / cfg.get("data_root", "../..")).resolve()
    batches = cfg.get("batches", {})
    if name not in batches:
        raise SystemExit(f"Batch '{name}' not in {batches_path}. Known: {sorted(batches)}")
    # Registered folders can overlap (a loose file at the drop root registers the
    # root itself, whose recursive glob then re-yields every deeper file under a
    # second route). Resolve per file: the deepest registered folder wins; equal
    # depth (root registered under both routes) falls back to the path hint.
    best = {}  # file -> (depth, route)
    for entry in batches[name]:
        route, folder = entry["route"], entry["folder"]
        p = Path(folder)
        base = p if p.is_absolute() else (data_root / folder)
        if not base.exists():
            print(f"  WARN: batch folder missing, skipped: {base}")
            continue
        exts = be.exts_for_route(route)
        depth = len(base.resolve().parts)
        for f in base.rglob("*"):
            if f.is_file() and f.suffix.lower() in exts:
                cur = best.get(f)
                if cur is None or depth > cur[0]:
                    best[f] = (depth, route)
                elif depth == cur[0] and cur[1] != route and route_for_path(f) == route:
                    best[f] = (depth, route)
    for f in sorted(best):
        yield best[f][1], f


def discover_folder(folder: Path):
    """Every report file under a drop folder, route-tagged by hint."""
    exts = be.PDF_EXTS | be.XLSX_EXTS
    for f in sorted(folder.rglob("*")):
        low = str(f).lower()
        # Skip OCR-track quarantine and misfile quarantine folders: their files are
        # not live report slots (a "_misfiled_dups"/"_misfiled_reloc" copy is a
        # relocated redundant/misfiled file, kept only for reversibility). Routing
        # them by filename hint would re-triage them as spurious REDs.
        if f.is_file() and f.suffix.lower() in exts \
                and "need reviews" not in low and "_misfiled" not in low:
            yield route_for_path(f), f


def register_batch(name: str, jobs, batches_path: Path) -> None:
    """Write/refresh a batches.json entry from discovered (route, leaf-folder) pairs."""
    cfg = json.loads(batches_path.read_text(encoding="utf-8"))
    data_root = (ROOT / cfg.get("data_root", "../..")).resolve()
    pairs = sorted({(route, str(path.parent)) for route, path in jobs})
    entries = []
    for route, folder in pairs:
        try:
            rel = str(Path(folder).resolve().relative_to(data_root)).replace("\\", "/")
        except ValueError:
            rel = folder.replace("\\", "/")
        entries.append({"folder": rel, "route": route})
    cfg.setdefault("batches", {})[name] = entries
    batches_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"  registered batch '{name}' ({len(entries)} folder/route entries) in {batches_path.name}")


def _division_hint(path: Path) -> str:
    import re
    m = re.match(r"^([A-Za-z][A-Za-z -]*?)_\[Sample\]_", path.name)
    return m.group(1).strip().upper() if m else ""


# --------------------------------------------------------------------------- #
# orchestrator
# --------------------------------------------------------------------------- #
class Runner:
    def __init__(self, args):
        self.args = args
        self.batch = args.batch or (Path(args.folder).name if args.folder else "batch")
        self.batches_path = Path(args.batches)
        self.out_dir = Path(args.out) if args.out else (ROOT / "_triage" / self.batch)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.record = {"batch": self.batch, "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
                       "phases_run": [], "warnings": []}
        self.jobs = []          # [(route, Path)]
        self.results = {}       # {str(path): result}
        self.triage_rows = []

    def log(self, msg):
        print(msg)

    # -- phase 1 -------------------------------------------------------------
    def phase_inspect(self):
        if self.args.batch:
            self.jobs = list(iter_batch(self.args.batch, self.batches_path))
        else:
            folder = Path(self.args.folder)
            if not folder.exists():
                raise SystemExit(f"Folder not found: {folder}")
            self.jobs = list(discover_folder(folder))
            if self.args.register:
                register_batch(self.batch, self.jobs, self.batches_path)
        if not self.jobs:
            raise SystemExit("No report files found.")
        split = Counter(route for route, _ in self.jobs)
        self.record["total_files"] = len(self.jobs)
        self.record["route_split"] = dict(split)
        self.log(f"  {len(self.jobs)} files  " + "  ".join(f"{r}:{n}" for r, n in sorted(split.items())))

    # -- phase 2 -------------------------------------------------------------
    def phase_extract(self):
        t0 = time.time()
        self.results = be.extract_batch(self.jobs, workers=self.args.workers,
                                        refresh=self.args.refresh, progress=True)
        errs = sum(1 for r in self.results.values() if r.get("_extract_error"))
        self.record["extract_seconds"] = round(time.time() - t0, 1)
        self.record["extract_errors"] = errs
        self.log(f"  extracted {len(self.results)} files in {self.record['extract_seconds']}s "
                 f"({errs} unreadable)")

    # -- phase 3 -------------------------------------------------------------
    def phase_triage(self):
        t0 = time.time()
        jobs = [(route, path.parent.name, path.name, str(path)) for route, path in self.jobs]
        workers = max(1, int(self.args.workers or 1))
        rows = [None] * len(jobs)
        # triage is CPU-bound (per-file catalog fuzzy-match in build_quality), so fan it
        # out the same way extraction does. Workers reload from the shared cache.
        if workers <= 1 or len(jobs) <= 2:
            for i, job in enumerate(jobs):
                rows[i] = _triage_one_cached(job)
        else:
            from concurrent.futures import ProcessPoolExecutor, as_completed
            try:
                with ProcessPoolExecutor(max_workers=workers) as ex:
                    futs = {ex.submit(_triage_one_cached, job): i for i, job in enumerate(jobs)}
                    done = 0
                    for fut in as_completed(futs):
                        rows[futs[fut]] = fut.result()
                        done += 1
                        if done % 100 == 0 or done == len(jobs):
                            self.log(f"    triaged {done}/{len(jobs)}")
            except Exception as exc:  # spawn trouble -> finish serially, never lose the phase
                self.log(f"    parallel triage failed ({exc}); serial fallback")
                for i, job in enumerate(jobs):
                    if rows[i] is None:
                        rows[i] = _triage_one_cached(job)
        self.triage_rows = rows
        buckets = Counter(r["bucket"] for r in rows)
        self.record["buckets"] = dict(buckets)
        self.record["triage_rows"] = rows
        self.record["clusters"] = self._clusters(rows)
        self.record["triage_seconds"] = round(time.time() - t0, 1)
        green = buckets.get("GREEN", 0)
        total = len(rows)
        self.record["green_pct"] = round(100 * green / total) if total else 0
        self.log(f"  GREEN {buckets.get('GREEN',0)}  AMBER {buckets.get('AMBER',0)}  "
                 f"RED {buckets.get('RED',0)}  ERROR {buckets.get('ERROR',0)}  "
                 f"({self.record['green_pct']}% green)  [{self.record['triage_seconds']}s]")
        self.log(f"  {len(self.record['clusters'])} distinct cluster(s) need work")

    def _clusters(self, rows):
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
            meta = bc.fix_meta(g["reason_code"])
            g["buckets"] = dict(g["buckets"])
            g.update(meta)
            out.append(g)
        # leverage = files affected, weighting code-fixable clusters above per-file (OCR) ones
        out.sort(key=lambda g: (g["count"] * (1.0 if g["code_fixable"] else 0.4)), reverse=True)
        # green-gain estimate: files in the top code-fixable clusters
        top_fixable = [g for g in out if g["code_fixable"]][:4]
        self.record["est_green_gain"] = sum(g["count"] for g in top_fixable)
        self.record["est_green_gain_clusters"] = len(top_fixable)
        return out

    # -- phase 4 -------------------------------------------------------------
    def phase_relocate(self):
        cands = []
        for route, path in self.jobs:
            res = self.results.get(str(path), {})
            if res.get("_extract_error"):
                continue
            ls, lp = bc.classify_misfiled(res)
            side = "stock" if route.startswith("stock") else "party"
            if side == "party" and ls and not lp:
                cands.append({"file": path.name, "from": "party", "to": "stock", "path": str(path)})
            elif side == "stock" and lp and not ls:
                cands.append({"file": path.name, "from": "stock", "to": "party", "path": str(path)})
        self.record["misfiled"] = cands
        self.log(f"  {len(cands)} misfiled candidate(s) (party<->stock)")
        if cands and self.args.apply_relocate and self.args.batch is None and self.args.folder:
            # delegate the actual move to the existing CLI (identical move + log)
            batch_date = Path(self.args.folder).name
            self.log("  --apply-relocate: delegating move to relocate_misfiled_reports.py")
            self._sh(["scripts/relocate_misfiled_reports.py", "--batch", batch_date, "--apply"])
        elif cands and self.args.apply_relocate:
            self.record["warnings"].append("apply-relocate needs --folder (a dated batch dir); skipped move.")

    # -- phase 5 -------------------------------------------------------------
    def phase_headers(self):
        agg = {"party": {}, "stock": {}}
        for route, path in self.jobs:
            res = self.results.get(str(path), {})
            if res.get("_extract_error"):
                continue
            rt = bc.report_type(route)
            for item in bc.analyze_unmapped_headers(res, rt, self.args.header_min_score):
                b = agg[rt].setdefault(item["norm"], {"header": item["header"], "norm": item["norm"],
                                                      "count": 0, "guess": item["guess"],
                                                      "score": item["score"], "example": path.name})
                b["count"] += 1
                if item["score"] > b["score"]:
                    b["guess"], b["score"] = item["guess"], item["score"]
        out = {}
        for rt in ("party", "stock"):
            items = sorted(agg[rt].values(), key=lambda b: (-b["count"], b["header"].lower()))
            out[rt] = items
        self.record["unmapped_headers"] = out
        n = len(out["party"]) + len(out["stock"])
        self.log(f"  {n} distinct unmapped header(s) — candidates for canonical.py (editorial; stays a candidate)")

    # -- phase 6 -------------------------------------------------------------
    def phase_products(self):
        spellings = {}
        for route, path in self.jobs:
            res = self.results.get(str(path), {})
            if res.get("_extract_error"):
                continue
            div = _division_hint(path)
            for name in bc.harvest_spellings(res):
                spellings.setdefault(name, div)
        catalog = json.loads((ROOT / "data" / "product_master.json").read_text(encoding="utf-8"))
        scan = bc.match_spellings_to_master(spellings, catalog,
                                            self.args.product_min_score, self.args.product_margin)
        self.record["products"] = {
            "distinct_spellings": len(spellings),
            "synonym_candidates": scan["added_count"],
            "products_touched": len(scan["added"]),
            "unmatched": len(scan["unmatched"]),
            "noise": scan["noise_count"],
            "catalog_size": len(catalog),
            "added_sample": dict(list(scan["added"].items())[:15]),
        }
        self.log(f"  {len(spellings)} spellings -> {scan['added_count']} synonym candidate(s) "
                 f"across {len(scan['added'])} products; {len(scan['unmatched'])} unmatched (new-product candidates)")
        if self.args.apply_products and scan["added_count"]:
            self.log("  --apply-products: delegating to build_product_synonyms.py --apply")
            data_root = Path(self.args.folder) if self.args.folder else None
            cmd = ["scripts/build_product_synonyms.py", "--apply",
                   "--min-score", str(self.args.product_min_score),
                   "--margin", str(self.args.product_margin)]
            if data_root:
                cmd += ["--data-root", str(data_root)]
            self._sh(cmd)
            # the catalog changed -> drop the in-process master cache so triage's
            # master-match reflects the new catalog on any later phase/re-run
            import core.product_master as pm
            pm._PRODUCT_MASTER = None

    # -- phase 7 -------------------------------------------------------------
    def phase_regression(self):
        manifest = json.loads((ROOT / "tests" / "regression_manifest.json").read_text(encoding="utf-8"))
        reports_root = (ROOT / manifest.get("reports_root", "../..")).resolve()
        suites = manifest["suites"]
        # default: only curated `files:` suites (fast); --reg-all includes glob suites
        want = self.args.reg_suites
        chosen = {}
        for name, cfg in suites.items():
            if want:
                if name in want:
                    chosen[name] = cfg
            elif "files" in cfg or self.args.reg_all:
                chosen[name] = cfg
        results = []
        baselines = ROOT / "tests" / "baselines"
        for name, cfg in chosen.items():
            route = cfg["route"]
            files = self._suite_files(cfg, reports_root)
            if not files:
                continue
            jobs = [(route, p) for p in files]
            res = be.extract_batch(jobs, workers=self.args.workers, progress=False)
            p = f = miss = 0
            moved_fields = Counter()
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
                        moved_fields[k] += 1
                else:
                    p += 1
            results.append({"suite": name, "passed": p, "failed": f, "missing": miss,
                            "fields_moved": dict(moved_fields)})
            if self.args.update_baselines and f:
                self.log(f"  --update-baselines: refreshing {name}")
                self._sh(["scripts/regression_test.py", "--suite", name, "--update"])
        self.record["regression"] = results
        tot_p = sum(r["passed"] for r in results)
        tot_f = sum(r["failed"] for r in results)
        self.log(f"  regression: {tot_p} pass / {tot_f} fail across {len(results)} curated suite(s)")

    def _suite_files(self, cfg, reports_root):
        route = cfg["route"]
        exts = be.exts_for_route(route)
        out = []
        if "files" in cfg:
            for rel in cfg["files"]:
                p = (reports_root / rel).resolve()
                if p.is_file() and p.suffix.lower() in exts:
                    out.append(p)
            return out
        pattern = cfg["glob"]
        head = pattern.split("*.", 1)[0].rstrip("/") if "*." in pattern else pattern
        base = reports_root / head
        if base.exists():
            out = [p for p in sorted(base.glob("*")) if p.is_file() and p.suffix.lower() in exts]
        return out

    # -- phase 8 -------------------------------------------------------------
    def phase_quarantine(self):
        q = [r for r in self.triage_rows if r["reason_code"] in ("SCANNED_OR_EMPTY", "EXTRACTION_CRASHED")]
        self.record["quarantine"] = [{"file": r["file_name"], "reason": r["reason_code"],
                                      "route": r["route"], "path": r["path"]} for r in q]
        self.log(f"  {len(q)} file(s) for OCR/manual review (scanned/empty or crashed)")
        if q and self.args.apply_quarantine:
            self._do_quarantine(q)

    def _do_quarantine(self, q):
        import os, shutil
        if self.args.folder:
            batch_dir = Path(self.args.folder)
        else:
            # infer from the first job's path: .../<batch>/<party|stock root>/...
            batch_dir = Path(q[0]["path"]).parents[2]
        review = batch_dir / "need Reviews"
        dest = {"party": review / "party wise", "stock": review / "sales reports"}
        for d in dest.values():
            d.mkdir(parents=True, exist_ok=True)
        moved = 0
        for item in q:
            sp = item["path"]
            side = "party" if item["route"].startswith("party") else "stock"
            if sp and os.path.exists(sp):
                shutil.move(sp, str(dest[side] / Path(sp).name))
                moved += 1
        self.log(f"  --apply-quarantine: moved {moved} file(s) into {review}")

    # -- phase 9 -------------------------------------------------------------
    def phase_mirror(self):
        import filecmp
        status = {}
        for sub in ("core", "extractors"):
            a, b = PROJECTS / "Backends" / sub, PROJECTS / "Python-Service-UI" / sub
            status[sub] = self._dirs_equal(a, b)
        pm_a = PROJECTS / "Backends" / "data" / "product_master.json"
        pm_b = PROJECTS / "Python-Service-UI" / "data" / "product_master.json"
        status["product_master.json"] = pm_a.exists() and pm_b.exists() and filecmp.cmp(pm_a, pm_b, shallow=False)
        self.record["mirror"] = status
        ok = all(status.values())
        self.log(f"  engine mirror: {'IN SYNC' if ok else 'DRIFT — reconcile before deploy'}  "
                 + "  ".join(f"{k}:{'ok' if v else 'DIFF'}" for k, v in status.items()))

    def _dirs_equal(self, a: Path, b: Path) -> bool:
        if not a.exists() or not b.exists():
            return False
        import filecmp
        a_files = {p.relative_to(a).as_posix() for p in a.rglob("*.py")}
        b_files = {p.relative_to(b).as_posix() for p in b.rglob("*.py")}
        if a_files != b_files:
            return False
        for rel in a_files:
            if not filecmp.cmp(a / rel, b / rel, shallow=False):
                return False
        return True

    # -- phase 10 ------------------------------------------------------------
    def phase_dashboard(self):
        (self.out_dir / "run.json").write_text(
            json.dumps({k: v for k, v in self.record.items() if k != "triage_rows"},
                       indent=2, ensure_ascii=False), encoding="utf-8")
        # full record (incl. per-file rows) for the renderer
        rd.render(self.record, self.out_dir)
        self.log(f"  dashboard -> {self.out_dir / 'dashboard.html'}")
        self.log(f"  summary   -> {self.out_dir / 'SUMMARY.md'}")

    # -- helpers -------------------------------------------------------------
    def _sh(self, args):
        cmd = [PY, "-u"] + args
        print("    $ " + " ".join(args))
        subprocess.run(cmd, cwd=str(ROOT), check=False)

    def run(self, phases):
        order = [p for p in ALL_PHASES if p in phases]
        for ph in order:
            self.log(f"\n[{ph}]")
            getattr(self, f"phase_{ph}")()
            self.record["phases_run"].append(ph)


def _select_phases(args):
    phases = set(ALL_PHASES)
    if args.only:
        phases = set(args.only)
    if args.from_phase:
        i = ALL_PHASES.index(args.from_phase)
        phases = set(ALL_PHASES[i:])
    if args.skip:
        phases -= set(args.skip)
    # hard dependencies: most phases need extraction + the job list
    if phases & {"triage", "relocate", "headers", "products", "regression", "quarantine"}:
        phases |= {"inspect", "extract"}
    if "triage" not in phases and "quarantine" in phases:
        phases |= {"triage"}
    if "dashboard" in phases:
        phases |= {"inspect", "extract", "triage"}
    return phases


def main() -> int:
    ap = argparse.ArgumentParser(description="One-command batch pipeline (extract once, all phases, one dashboard)")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--batch", help="Named batch from batches.json")
    src.add_argument("--folder", help="A drop folder (auto-discovers routes)")
    ap.add_argument("--batches", default=str(ROOT / "batches.json"))
    ap.add_argument("--out", default=None, help="Output dir (default _triage/<batch>)")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--refresh", action="store_true", help="Ignore the extract cache")
    ap.add_argument("--register", action="store_true", help="With --folder: write a batches.json entry")
    ap.add_argument("--only", nargs="+", choices=ALL_PHASES, help="Run only these phases")
    ap.add_argument("--skip", nargs="+", choices=ALL_PHASES, help="Skip these phases")
    ap.add_argument("--from", dest="from_phase", choices=ALL_PHASES, help="Run from this phase on")
    # gates (default off -> candidates only)
    ap.add_argument("--apply-relocate", action="store_true", help="GATE: move misfiled files")
    ap.add_argument("--apply-products", action="store_true", help="GATE: write product_master.json synonyms")
    ap.add_argument("--apply-quarantine", action="store_true", help="GATE: move scanned/corrupt into need Reviews")
    ap.add_argument("--update-baselines", action="store_true", help="GATE: refresh regression baselines on failing suites")
    # tuning
    ap.add_argument("--header-min-score", type=float, default=0.62)
    ap.add_argument("--product-min-score", type=float, default=0.90)
    ap.add_argument("--product-margin", type=float, default=0.03)
    ap.add_argument("--reg-suites", nargs="+", help="Regression: only these suites")
    ap.add_argument("--reg-all", action="store_true", help="Regression: include slow glob suites too")
    args = ap.parse_args()

    phases = _select_phases(args)
    runner = Runner(args)
    print(f"=== run_batch: {runner.batch}  (phases: {', '.join(p for p in ALL_PHASES if p in phases)}) ===")
    t0 = time.time()
    runner.run(phases)
    print(f"\nDone in {round(time.time() - t0, 1)}s.  Open: {runner.out_dir / 'dashboard.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
