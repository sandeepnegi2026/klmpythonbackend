#!/usr/bin/env python3
"""
Batch triage runner — score & bucket EVERY vendor sample in one pass.

This is the "test all 2,000 samples without opening them one by one" tool. It
runs the real extractors over a folder (or the regression manifest's Data tree),
applies core.quality.build_quality to each file, and emits:

  * a sortable CSV  (one row per file: bucket, reason, score, all cross-checks)
  * a color-coded HTML report (GREEN / AMBER / RED), and
  * a CLUSTER section grouping RED+AMBER files by (route, layout fingerprint) —
    THIS is the actual work-list: a few dozen distinct layouts to fix, not
    thousands of files. Fix one parser, every vendor sharing that fingerprint
    flips to GREEN on the next run.

Usage:
  # one route over a drop folder (recurses)
  python scripts/triage_batch.py --folder "D:/Data/Party Wise/CG" --route party_pdf

  # everything in the regression manifest's Data tree, all routes
  python scripts/triage_batch.py --manifest

  # just one curated date-wise suite — only the verified files, runs in seconds
  python scripts/triage_batch.py --suite 26june_party_pdf

  # a named batch from batches.json (all its routes) — incremental cache:
  # a re-run only re-extracts NEW/changed files; a parser change busts the cache.
  python scripts/triage_batch.py --batch 26_june --workers 6
  python scripts/triage_batch.py --batch 26_june --refresh   # force full re-extract

  # tune output location / parallelism
  python scripts/triage_batch.py --manifest --out ./_triage --workers 6

Buckets come straight from core/triage.py THRESHOLDS — tune there, re-run, compare.

(A --from-db mode that pulls vendor_sample_reports rows and downloads each file
from the `vendor-onboarding-samples` bucket is sketched at the bottom; it needs
Supabase credentials and is intentionally left as a documented extension so this
script runs offline against local files today.)
"""
from __future__ import annotations

import argparse
import os
import csv
import hashlib
import html
import json
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.quality import build_quality  # noqa: E402
from extractors import party_pdf, party_xlsx, stock_pdf, stock_xlsx  # noqa: E402

ROUTES = {
    "party_pdf": party_pdf.extract,
    "party_xlsx": party_xlsx.extract,
    "stock_pdf": stock_pdf.extract,
    "stock_xlsx": stock_xlsx.extract,
}
PDF_EXTS = {".pdf"}
XLSX_EXTS = {".xlsx", ".xls", ".xlsm"}
BUCKET_ORDER = {"RED": 0, "AMBER": 1, "GREEN": 2, "ERROR": -1}
BUCKET_COLOR = {"GREEN": "#d7f5dd", "AMBER": "#fff3cd", "RED": "#f8d7da", "ERROR": "#e2e3e5"}


def _report_type(route: str) -> str:
    return "stock" if route.startswith("stock") else "party"


def _exts_for_route(route: str) -> set[str]:
    return PDF_EXTS if route.endswith("pdf") else XLSX_EXTS


# --------------------------------------------------------------------------- #
# file discovery
# --------------------------------------------------------------------------- #
def _iter_folder(folder: Path, route: str):
    exts = _exts_for_route(route)
    for path in sorted(folder.rglob("*")):
        if path.is_file() and path.suffix.lower() in exts:
            yield route, path


def _iter_manifest(suite_names=None):
    """Reuse the regression manifest's suites (route + glob/files over the Data tree).

    With `suite_names` (a list), only those suites are triaged — the fast curated
    path, e.g. --suite 26june_party_pdf runs just the verified New Data files.
    A suite may define either a folder `glob` (whole batch) or an explicit
    `files` list (curated verified samples); both are supported here.
    """
    manifest_path = ROOT / "tests" / "regression_manifest.json"
    with manifest_path.open(encoding="utf-8") as fh:
        manifest = json.load(fh)
    reports_root = (ROOT / manifest.get("reports_root", "../..")).resolve()
    suites = manifest["suites"]
    names = suite_names if suite_names else list(suites)
    for name in names:
        cfg = suites.get(name)
        if cfg is None:
            print(f"  WARN: unknown suite '{name}', skipped (known: {', '.join(sorted(suites))})")
            continue
        route = cfg["route"]
        exts = _exts_for_route(route)
        if "files" in cfg:
            for rel in cfg["files"]:
                path = (reports_root / rel).resolve()
                if path.is_file() and path.suffix.lower() in exts:
                    yield route, path
            continue
        pattern = cfg["glob"]
        head = pattern.split("*.", 1)[0].rstrip("/") if "*." in pattern else pattern
        base = reports_root / head
        if not base.exists():
            continue
        for path in sorted(base.glob("*")):
            if path.is_file() and path.suffix.lower() in exts:
                yield route, path


def _iter_batch(name: str, batches_path: str):
    """Yield (route, path) for every folder/route entry in a named batch.

    Lets a new vendor drop be triaged with `--batch <name>` instead of copying
    this script per batch — add one entry to batches.json and run.
    """
    cfg = json.loads(Path(batches_path).read_text(encoding="utf-8"))
    data_root = (ROOT / cfg.get("data_root", "../..")).resolve()
    batches = cfg.get("batches", {})
    if name not in batches:
        raise SystemExit(f"Batch '{name}' not in {batches_path}. Known: {sorted(batches)}")
    for entry in batches[name]:
        route, folder = entry["route"], entry["folder"]
        p = Path(folder)
        base = p if p.is_absolute() else (data_root / folder)
        if not base.exists():
            print(f"  WARN: batch folder missing, skipped: {base}")
            continue
        yield from _iter_folder(base, route)


# --------------------------------------------------------------------------- #
# incremental cache — skip files already triaged under the current parser code
# --------------------------------------------------------------------------- #
def _job_key(route: str, data: bytes) -> str:
    return f"{route}:{hashlib.sha1(data).hexdigest()}"


def _code_sig() -> str:
    """Fingerprint extractor + core source so any parser change auto-busts the cache."""
    h = hashlib.sha1()
    for sub in ("extractors", "core"):
        base = ROOT / sub
        if not base.exists():
            continue
        for p in sorted(base.rglob("*.py")):
            h.update(p.relative_to(ROOT).as_posix().encode())
            h.update(p.read_bytes())
    return h.hexdigest()[:16]


def _load_cache(path: Path, code_sig: str, refresh: bool) -> dict:
    if refresh or not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if data.get("code_sig") != code_sig:   # parser/core changed -> stale, re-triage all
        return {}
    return data.get("entries", {})


def _save_cache(path: Path, code_sig: str, entries: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"code_sig": code_sig, "entries": entries}), encoding="utf-8")


# --------------------------------------------------------------------------- #
# per-file triage
# --------------------------------------------------------------------------- #
def triage_one(route: str, path: Path) -> dict:
    base = {
        "vendor": path.parent.name,
        "file_name": path.name,
        "route": route,
        "path": str(path),
    }
    try:
        result = ROUTES[route](path.read_bytes(), {"filename": path.name}) or {}
        quality = build_quality(result, _report_type(route))
        debug = result.get("debug") or {}
        checks = quality["checks"]
        triage = quality["triage"]
        sanity = checks.get("sanity") or {}
        return {
            **base,
            "layout": debug.get("layout") or debug.get("detected_format") or "unknown",
            "bucket": triage["bucket"],
            "reason_code": triage["reason_code"],
            "reason": triage["reason"],
            "score_pct": quality["score_pct"],
            "row_count": checks["row_count"],
            "sanity_eff": sanity.get("effective_pass_rate"),
            "master_match": checks.get("product_master_match_rate"),
            "dup_ratio": checks.get("duplicate_row_ratio"),
            "zero_fill": checks.get("zero_fill_ratio"),
            "soft_missing": ", ".join(checks.get("soft_missing") or []),
            "warnings": len(result.get("warnings") or []),
        }
    except Exception as exc:  # a single bad file must never kill the batch
        return {
            **base,
            "layout": "ERROR",
            "bucket": "ERROR",
            "reason_code": "EXTRACTION_CRASHED",
            "reason": f"{type(exc).__name__}: {exc}",
            "score_pct": None,
            "row_count": None,
            "sanity_eff": None,
            "master_match": None,
            "dup_ratio": None,
            "zero_fill": None,
            "warnings": None,
        }


def _run(jobs, workers: int, cache: dict, refresh: bool):
    """Triage each job, reusing cached verdicts for unchanged files.

    `cache` maps job-key -> stored row and is updated in place. The job-key is
    route + SHA1(file bytes); the whole cache is discarded by _load_cache when the
    extractor/core code changes, so a hit always reflects the current parser.
    Only cache MISSES pay the expensive extraction; hits cost just a read + hash.
    """
    results = [None] * len(jobs)
    misses = []  # (idx, route, path, key)
    hits = 0
    for idx, (route, path) in enumerate(jobs):
        key = _job_key(route, path.read_bytes())
        ent = None if refresh else cache.get(key)
        if ent is not None:
            row = dict(ent)
            row.update(vendor=path.parent.name, file_name=path.name, path=str(path), route=route)
            results[idx] = row
            hits += 1
        else:
            misses.append((idx, route, path, key))

    if hits:
        print(f"  {hits} file(s) reused from cache, {len(misses)} to (re)extract\n")

    if workers <= 1 or len(misses) <= 1:
        for n, (idx, route, path, key) in enumerate(misses, 1):
            row = triage_one(route, path)
            print(f"  [{n}] {row['bucket']:6} {row['reason_code']:28} {row['file_name']}")
            cache[key] = dict(row)
            results[idx] = row
    else:
        # parallel: extraction is CPU-bound, so a process pool helps on the backlog
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(max_workers=workers) as ex:
            futs = [(idx, key, ex.submit(triage_one, route, path))
                    for idx, route, path, key in misses]
            for n, (idx, key, fut) in enumerate(futs, 1):
                row = fut.result()
                print(f"  [{n}] {row['bucket']:6} {row['reason_code']:28} {row['file_name']}")
                cache[key] = dict(row)
                results[idx] = row
    return results


# --------------------------------------------------------------------------- #
# output
# --------------------------------------------------------------------------- #
COLUMNS = [
    "vendor", "file_name", "route", "layout", "bucket", "reason_code", "reason",
    "score_pct", "row_count", "sanity_eff", "master_match", "dup_ratio",
    "zero_fill", "soft_missing", "warnings", "path",
]


def _write_csv(rows, out_csv: Path):
    with out_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in COLUMNS})


def _clusters(rows):
    """Group the files that need work by (route, layout) — the real work-list."""
    groups: dict[tuple, dict] = {}
    for row in rows:
        if row["bucket"] in ("GREEN",):
            continue
        key = (row["route"], row["layout"])
        g = groups.setdefault(key, {"count": 0, "buckets": {}, "example": row["file_name"], "reason": row["reason_code"]})
        g["count"] += 1
        g["buckets"][row["bucket"]] = g["buckets"].get(row["bucket"], 0) + 1
    return sorted(groups.items(), key=lambda kv: kv[1]["count"], reverse=True)


def _write_html(rows, summary, clusters, out_html: Path):
    def td(v):
        return f"<td>{html.escape('' if v is None else str(v))}</td>"

    parts = [
        "<!doctype html><meta charset='utf-8'><title>Sample triage report</title>",
        "<style>body{font:13px system-ui,Segoe UI,Arial;margin:24px}"
        "table{border-collapse:collapse;width:100%}th,td{border:1px solid #ccc;padding:4px 6px;text-align:left}"
        "th{background:#f0f0f0;position:sticky;top:0}h2{margin-top:28px}"
        ".pill{padding:2px 8px;border-radius:10px;font-weight:600}</style>",
        f"<h1>Sample triage report</h1><p>{html.escape(summary['generated'])} — "
        f"{summary['total']} files</p>",
        "<p>"
        + " ".join(
            f"<span class='pill' style='background:{BUCKET_COLOR.get(b)}'>{b}: {summary['buckets'].get(b, 0)}</span>"
            for b in ("GREEN", "AMBER", "RED", "ERROR")
        )
        + "</p>",
        "<h2>Work-list — distinct layouts needing attention (most files first)</h2>",
        "<table><tr><th>#</th><th>route</th><th>layout fingerprint</th><th>files</th>"
        "<th>buckets</th><th>top reason</th><th>example file</th></tr>",
    ]
    for i, ((route, layout), g) in enumerate(clusters, 1):
        buckets = ", ".join(f"{b}:{n}" for b, n in sorted(g["buckets"].items()))
        parts.append(
            f"<tr><td>{i}</td><td>{html.escape(route)}</td><td><code>{html.escape(str(layout))}</code></td>"
            f"<td>{g['count']}</td><td>{html.escape(buckets)}</td><td>{html.escape(g['reason'])}</td>"
            f"<td>{html.escape(g['example'])}</td></tr>"
        )
    parts.append("</table>")

    parts.append("<h2>All files</h2><table><tr>" + "".join(f"<th>{c}</th>" for c in COLUMNS) + "</tr>")
    for row in rows:
        color = BUCKET_COLOR.get(row["bucket"], "#fff")
        parts.append(f"<tr style='background:{color}'>" + "".join(td(row.get(c)) for c in COLUMNS) + "</tr>")
    parts.append("</table>")
    out_html.write_text("".join(parts), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Batch triage runner for vendor samples")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--folder", help="Folder of sample files (recurses)")
    src.add_argument("--manifest", action="store_true", help="Use tests/regression_manifest.json Data tree, all routes")
    src.add_argument("--suite", action="append", help="Triage only named manifest suite(s), e.g. 26june_party_pdf (curated verified files — fast)")
    src.add_argument("--batch", help="Named batch from batches.json (runs all its folder/route entries)")
    ap.add_argument("--route", choices=sorted(ROUTES), help="Required with --folder")
    ap.add_argument("--batches", default=str(ROOT / "batches.json"), help="Batch registry file (used with --batch)")
    ap.add_argument("--out", default=None, help="Output directory (default: _triage, or _triage/<batch>)")
    ap.add_argument("--workers", type=int, default=min(16, max(1, (os.cpu_count() or 4) - 2)),
                    help="Parallel worker processes (default: auto = min(16, cores-2))")
    ap.add_argument("--refresh", action="store_true", help="Ignore the cache and re-extract every file")
    args = ap.parse_args()

    if args.folder and not args.route:
        ap.error("--route is required with --folder")

    if args.folder:
        folder = Path(args.folder)
        if not folder.exists():
            print(f"Folder not found: {folder}")
            return 2
        jobs = list(_iter_folder(folder, args.route))
        out_default = ROOT / "_triage"
    elif args.batch:
        jobs = list(_iter_batch(args.batch, args.batches))
        out_default = ROOT / "_triage" / args.batch
    elif args.suite:
        jobs = list(_iter_manifest(args.suite))
        out_default = ROOT / "_triage" / "_".join(args.suite)
    else:
        jobs = list(_iter_manifest())
        out_default = ROOT / "_triage"

    if not jobs:
        print("No matching files found.")
        return 2

    out_dir = Path(args.out) if args.out else out_default
    out_dir.mkdir(parents=True, exist_ok=True)

    code_sig = _code_sig()
    cache_path = out_dir / ".triage_cache.json"
    cache = _load_cache(cache_path, code_sig, args.refresh)

    print(f"Triaging {len(jobs)} file(s) with {args.workers} worker(s)"
          f"{' [--refresh]' if args.refresh else ''}...\n")
    rows = _run(jobs, args.workers, cache, args.refresh)
    _save_cache(cache_path, code_sig, cache)
    rows.sort(key=lambda r: (BUCKET_ORDER.get(r["bucket"], 9), r["route"], r["reason_code"], r["file_name"]))

    buckets: dict[str, int] = {}
    for row in rows:
        buckets[row["bucket"]] = buckets.get(row["bucket"], 0) + 1

    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_csv = out_dir / f"triage_report_{stamp}.csv"
    out_html = out_dir / f"triage_report_{stamp}.html"
    clusters = _clusters(rows)
    summary = {"generated": stamp, "total": len(rows), "buckets": buckets}
    _write_csv(rows, out_csv)
    _write_html(rows, summary, clusters, out_html)

    print("\n" + "=" * 60)
    for b in ("GREEN", "AMBER", "RED", "ERROR"):
        if buckets.get(b):
            print(f"  {b:6}: {buckets[b]}")
    print(f"\n  {len(clusters)} distinct layout(s) need attention (see HTML work-list).")
    print(f"  CSV : {out_csv}")
    print(f"  HTML: {out_html}")
    print(f"  cache: {cache_path}")
    return 0


# --------------------------------------------------------------------------- #
# --from-db extension (documented; not wired to avoid prod creds in this script)
# --------------------------------------------------------------------------- #
# To triage what vendors have actually uploaded rather than a local folder:
#   1. Query vendor_sample_reports (id, vendor_id, format_type, file_path,
#      file_name, division_id) — join vendors for the name.
#   2. Download each file_path from the `vendor-onboarding-samples` storage
#      bucket using the service-role key (same token the edge functions use:
#      SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY, both already in Backends/.env).
#   3. Map format_type -> route (party_product_* -> party_*, stock_sales_* ->
#      stock_*) and feed (route, bytes, file_name) through triage_one's body.
#   4. Optionally write triage_bucket/reason/score back to the row (local DB
#      only — see plan Phase 5 migration).
# Keeping this offline-first means the tool works today without any credentials.

if __name__ == "__main__":
    raise SystemExit(main())
