#!/usr/bin/env python3
"""
Scan every real vendor report for column headers that do NOT map to a canonical
field, so they can be added as synonyms in core/canonical.py.

Walks the entire Data tree, runs the existing route extractors over every
PDF/Excel report, collects every distinct source header each route reports in
`headers_detected`, and re-runs core.header_match.match_header() over each one.
Headers that match no canonical field (or only the generic `raw_*` fallback) are
collected, grouped by report_type (party / stock), with a best-guess target
field + score to help decide which canonical synonym list to extend.

This is a REPORT generator. It deliberately does NOT edit canonical.py:
choosing which canonical field an unmapped header belongs to is an editorial
decision (see AGENTS.md - canonical.py is a "High" risk, all-routes change).
The script only ever reads reports and writes the unmapped_headers.json report.

Per AGENTS.md, adding header synonyms is a DATA/mapping change, not a parser
change: run scripts/regression_test.py before and after editing canonical.py.

Usage:
  python scripts/build_header_synonyms.py                 # scan, write unmapped_headers.json
  python scripts/build_header_synonyms.py --data-root "D:/Devs/Reports/Data"
  python scripts/build_header_synonyms.py --min-score 0.62  # match threshold (default mirrors header_match)
  python scripts/build_header_synonyms.py --no-write        # print only, write nothing
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # .../Projects/Backends
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.header_match import match_header, normalize

# Header detection happens *before* product-master enrichment in every pipeline,
# and enrichment (per-row fuzzy matching against the master) is the dominant cost.
# Neutralise it so this scan runs in a fraction of the time. We patch the module
# attribute *before* importing the pipelines, so their `from core.product_master
# import enrich_rows_with_master` binds to this no-op. (Scan-only; no source edit.)
import core.product_master as _pm
_pm.enrich_rows_with_master = lambda rows, *a, **k: rows

from extractors.party_pdf.pipeline import extract as extract_party_pdf
from extractors.party_xlsx.pipeline import extract as extract_party_xlsx
from extractors.stock_pdf.pipeline import extract as extract_stock_pdf
from extractors.stock_xlsx.pipeline import extract as extract_stock_xlsx

PROJECTS = ROOT.parent                              # .../Projects
DEFAULT_DATA_ROOT = PROJECTS.parent / "Data"        # .../Reports/Data

# unmapped_headers.json lives in both mirrors; keep them identical regardless of
# which mirror this script is run from.
REPORT_PATHS = [
    PROJECTS / "Backends" / "unmapped_headers.json",
    PROJECTS / "Python-Service-UI" / "unmapped_headers.json",
]

REPORT_EXTS = {".pdf", ".xls", ".xlsx"}             # everything else is skipped


def _route_for(path: Path):
    """Pick (route_name, extractor, report_type) from folder hint + extension."""
    ext = path.suffix.lower()
    is_xlsx = ext in (".xls", ".xlsx")
    s = str(path).lower()
    # Folder/name hints. The "party_wise"/"_party_product" forms cover the
    # vendor-export drops (e.g. "party_wise-26 June", "..._party_product_xlsx"),
    # alongside the legacy "Party Wise/" tree. A stock hint (e.g. the
    # "sales and stock" folder, "_stock_sales" suffix) overrides, so a
    # "STOCK-SALES ..._party_product" file under party_wise still routes party.
    party_hint = ("party wise" in s) or ("party_wise" in s) or ("party_product" in s)
    stock_hint = ("sales and stock" in s) or ("stock and sales" in s) or ("stock_sales" in s)
    is_party = party_hint and not stock_hint
    if is_party:
        if is_xlsx:
            return "party_xlsx", extract_party_xlsx, "party"
        return "party_pdf", extract_party_pdf, "party"
    if is_xlsx:
        return "stock_xlsx", extract_stock_xlsx, "stock"
    return "stock_pdf", extract_stock_pdf, "stock"


def _enumerate_reports(data_root: Path) -> list[Path]:
    files: list[Path] = []
    for dirpath, _dirnames, filenames in os.walk(data_root):
        for name in filenames:
            if Path(name).suffix.lower() in REPORT_EXTS:
                files.append(Path(dirpath) / name)
    return sorted(files)


def main() -> int:
    ap = argparse.ArgumentParser(description="Report vendor headers that map to no canonical field")
    ap.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT), help="Root folder of vendor reports")
    ap.add_argument("--min-score", type=float, default=0.62,
                    help="Match threshold (mirrors header_match default); below this = unmapped")
    ap.add_argument("--no-write", action="store_true", help="Print summary only; do not write unmapped_headers.json")
    args = ap.parse_args()

    data_root = Path(args.data_root)
    if not data_root.exists():
        print(f"Data root not found: {data_root}")
        return 2

    files = _enumerate_reports(data_root)
    print(f"Scanning reports under: {data_root}")
    print(f"Found {len(files)} report files (.pdf/.xls/.xlsx)\n")

    # report_type -> normalized_header -> {"display":..., "files": set, "guess":..., "score":...}
    unmapped: dict[str, dict[str, dict]] = {"party": {}, "stock": {}}
    failures: list[tuple[str, str]] = []
    total = len(files)

    for idx, path in enumerate(files, 1):
        _route, extractor, report_type = _route_for(path)
        try:
            result = extractor(path.read_bytes(), {"filename": path.name})
        except Exception as exc:  # image-only PDF, corrupt/locked file, unreadable .xls, etc.
            failures.append((str(path), f"{type(exc).__name__}: {exc}"))
            continue

        for source_header in (result.get("headers_detected") or {}):
            header = str(source_header).strip()
            norm = normalize(header)
            if not norm:
                continue
            key, score, _method = match_header(header, report_type, min_score=args.min_score)
            if key is not None:
                continue  # already mapped to a canonical field
            guess, guess_score, _ = match_header(header, report_type, min_score=0.0)
            bucket = unmapped[report_type].setdefault(
                norm, {"display": header, "files": set(), "guess": guess, "score": round(guess_score, 3)}
            )
            bucket["files"].add(path.name)
            if guess_score > bucket["score"]:
                bucket["guess"], bucket["score"] = guess, round(guess_score, 3)

        if idx % 25 == 0 or idx == total:
            n_party = len(unmapped["party"])
            n_stock = len(unmapped["stock"])
            print(f"  ...{idx}/{total} files  (unmapped party: {n_party}, stock: {n_stock}, failed: {len(failures)})")

    # ---- Report -------------------------------------------------------------
    print("\n" + "=" * 72)
    print("UNMAPPED HEADERS (match no canonical field at threshold "
          f"{args.min_score})")
    print("=" * 72)
    out: dict[str, dict] = {}
    for report_type in ("party", "stock"):
        items = sorted(unmapped[report_type].values(), key=lambda b: (-len(b["files"]), b["display"].lower()))
        print(f"\n--- {report_type.upper()} ({len(items)} distinct unmapped headers) ---")
        section: dict[str, dict] = {}
        for b in items:
            files_sorted = sorted(b["files"])
            print(f"  {b['display']!r:32} x{len(files_sorted):<4} "
                  f"closest: {b['guess']} ({b['score']})   e.g. {files_sorted[0]}")
            section[b["display"]] = {
                "report_type": report_type,
                "count": len(files_sorted),
                "closest_field": b["guess"],
                "closest_score": b["score"],
                "files": files_sorted,
            }
        out[report_type] = section

    if failures:
        print(f"\n{len(failures)} files failed to extract (image-only/corrupt/locked).")
        fail_report = ROOT / "scripts" / "_header_scan_failures.txt"
        with fail_report.open("w", encoding="utf-8") as fh:
            fh.write(f"# {len(failures)} files failed to extract\n\n")
            for p, err in failures:
                fh.write(f"{p}\t{err}\n")
        print(f"Failures logged to {fail_report}")

    if args.no_write:
        print("\n--no-write: unmapped_headers.json not written.")
        return 0

    payload = json.dumps(out, indent=2, ensure_ascii=False) + "\n"
    for report_path in REPORT_PATHS:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with report_path.open("w", encoding="utf-8") as fh:
            fh.write(payload)
        print(f"\nWrote {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
