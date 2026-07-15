#!/usr/bin/env python3
"""
Regression probe for the product_party_banded detector: for every file under a
folder, compute detect_layout() WITH the new detector active vs WITHOUT it (the new
detector monkeypatched to return False). Any file whose layout differs was affected
by the change. For affected files we also report party_name coverage before/after so
a "steal" (a working file made worse) is distinguishable from a genuine rescue.

Layout unchanged  => that file's extraction is byte-identical to before (the new
detector is the ONLY behavioral change; registry/label additions are inert unless the
layout key is selected).

Usage:
  python scripts/detect_diff.py --folder "<folder>"          # scan a folder (recursive)
  python scripts/detect_diff.py --list-file paths.txt        # scan an explicit \\n list
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# neutralise enrichment (irrelevant to detection / party_name presence, and slow)
import core.product_master as _pm  # noqa: E402
_pm.enrich_rows_with_master = lambda rows, *a, **k: rows

from extractors.party_xlsx.xlsx_io import load_rows  # noqa: E402
from extractors.party_xlsx import detect as _detect  # noqa: E402
from extractors.party_xlsx.registry import parse_rows  # noqa: E402
from extractors.party_xlsx.postprocess import cast_numbers  # noqa: E402
from core.canonical import enforce_schema  # noqa: E402
import extractors.party_xlsx.layouts.product_party_banded as _ppb  # noqa: E402

EXTS = {".xls", ".xlsx", ".xlsm"}


def _party_cov(rows_raw, layout):
    try:
        recs, _ = parse_rows(rows_raw, layout)
        cast_numbers(recs)
        enforce_schema(recs, "party")
    except Exception as exc:
        return f"ERROR:{type(exc).__name__}"
    if not recs:
        return "0/0"
    n = sum(1 for r in recs if str(r.get("party_name", "")).strip())
    return f"{n}/{len(recs)}"


def scan(files):
    changed = []
    errors = []
    total = 0
    orig_detect = _ppb.detect
    for f in files:
        total += 1
        try:
            _sn, rows = load_rows(f.read_bytes(), f.name, None)
        except Exception as exc:
            errors.append({"file": f.name, "err": f"load:{type(exc).__name__}"})
            continue
        # WITHOUT the new detector
        _ppb.detect = lambda rows: False
        _detect.__dict__  # no-op keep import
        try:
            layout_without = _detect.detect_layout(rows)
        finally:
            _ppb.detect = orig_detect
        # WITH the new detector (real)
        layout_with = _detect.detect_layout(rows)
        if layout_with != layout_without:
            changed.append({
                "file": f.name,
                "path": str(f),
                "layout_without": layout_without,
                "layout_with": layout_with,
                "party_cov_without": _party_cov(rows, layout_without),
                "party_cov_with": _party_cov(rows, layout_with),
            })
    return {"total": total, "changed": changed, "errors": errors}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder")
    ap.add_argument("--list-file")
    args = ap.parse_args()

    files = []
    if args.folder:
        for f in sorted(Path(args.folder).rglob("*")):
            if f.is_file() and f.suffix.lower() in EXTS and "need reviews" not in str(f).lower():
                files.append(f)
    if args.list_file:
        for line in Path(args.list_file).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and Path(line).is_file():
                files.append(Path(line))

    result = scan(files)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"\nSCANNED {result['total']}  CHANGED {len(result['changed'])}  ERRORS {len(result['errors'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
