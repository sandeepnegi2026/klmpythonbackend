#!/usr/bin/env python3
"""
Generate a per-file extraction report (Markdown + CSV) for one drop folder, in the
same format as `_triage/<batch>/per_file_report.md`. Reads each file's already-cached
extraction (fill it first with `run_batch --folder <folder> --only inspect extract`)
and re-triages it, so this is a fast, read-only pass — no re-extraction.

Usage:
  python scripts/gen_per_file_report.py --folder "<drop folder>" --out _triage/<name> --label "26 June Party Excel"
"""
from __future__ import annotations

import argparse
import csv
import io
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import batch_extract as be  # noqa: E402
import batch_core as bc  # noqa: E402
from run_batch import route_for_path  # noqa: E402

BUCKET_ORDER = ["GREEN", "AMBER", "RED", "ERROR"]


def _vendor_from_name(name: str) -> str:
    """Best-effort vendor label from the sample filename (mirrors the stock report)."""
    s = name
    s = re.sub(r"^\[Sample\]_", "", s)
    s = re.sub(r"^[A-Z]+_\[Sample\]_", "", s)  # division-prefixed samples
    s = re.sub(r"_(party_product|stock_sales)_(xlsx|pdf).*$", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\.(xls|xlsx|xlsm|pdf)$", "", s, flags=re.IGNORECASE)
    return s.replace("_", " ").strip()


def _fmt_sanity(v) -> str:
    if v is None:
        return "-"
    try:
        return str(round(float(v), 3))
    except (TypeError, ValueError):
        return "-"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--label", default=None, help="Title label, e.g. '26 June Party Excel'")
    args = ap.parse_args()

    folder = Path(args.folder)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    label = args.label or folder.name

    exts = be.PDF_EXTS | be.XLSX_EXTS
    files = sorted(
        f for f in folder.rglob("*")
        if f.is_file() and f.suffix.lower() in exts and "need reviews" not in str(f).lower()
    )

    rows = []
    misses = 0
    for f in files:
        route = route_for_path(f)
        try:
            result = be.get(route, str(f))
        except Exception as exc:  # not cached / unreadable -> mark and continue
            result = {"_extract_error": f"NOT_CACHED: {type(exc).__name__}: {exc}"}
            misses += 1
        tr = bc.triage_row(route, f.parent.name, f.name, str(f), result)
        rows.append(tr)

    buckets = Counter(r["bucket"] for r in rows)
    g, a, r_, e = (buckets.get(k, 0) for k in BUCKET_ORDER)

    # ---- Markdown ---------------------------------------------------------- #
    md = []
    md.append(f"# Per-file extraction report — {label}  ({len(rows)} files)\n")
    line = f"GREEN {g}  ·  AMBER {a}  ·  RED {r_}"
    if e:
        line += f"  ·  ERROR {e}"
    md.append(line + "\n\n")
    for bucket in BUCKET_ORDER:
        sub = sorted((x for x in rows if x["bucket"] == bucket), key=lambda x: x["file_name"].lower())
        if not sub:
            continue
        md.append(f"\n## {bucket} ({len(sub)})\n")
        md.append("| layout | rows | sanity | file | note |")
        md.append("|---|---|---|---|---|")
        for x in sub:
            note = "OK" if bucket == "GREEN" else (x.get("reason_code") or "")
            md.append(
                f"| {x.get('layout') or '?'} | {x.get('row_count') if x.get('row_count') is not None else '-'} "
                f"| {_fmt_sanity(x.get('sanity_eff'))} | {x['file_name']} | {note} |"
            )
        md.append("")
    (out / "per_file_report.md").write_text("\n".join(md), encoding="utf-8")

    # ---- CSV --------------------------------------------------------------- #
    with (out / "per_file_report.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["bucket", "code", "layout", "rows", "eff", "vendor", "file", "reason"])
        for bucket in BUCKET_ORDER:
            for x in sorted((y for y in rows if y["bucket"] == bucket), key=lambda y: y["file_name"].lower()):
                code = "OK" if bucket == "GREEN" else (x.get("reason_code") or "")
                w.writerow([
                    bucket, code, x.get("layout") or "", x.get("row_count") if x.get("row_count") is not None else "",
                    _fmt_sanity(x.get("sanity_eff")), _vendor_from_name(x["file_name"]),
                    x["file_name"], x.get("reason") or "",
                ])

    print(f"files={len(rows)}  GREEN {g}  AMBER {a}  RED {r_}  ERROR {e}  (not-cached: {misses})")
    print(f"wrote {out / 'per_file_report.md'}")
    print(f"wrote {out / 'per_file_report.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
