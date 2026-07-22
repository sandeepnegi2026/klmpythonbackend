"""Master-coverage + accuracy oracle.

The before/after yardstick for the exact-product remediation. Beyond the original
match-rate over the regression manifest, it reports the accuracy signals that are
INVISIBLE to a plain match-rate:

  * unmatched %                — rows the extractor could not resolve
  * form-mismatch count        — MATCHED rows whose raw form-group (cream/lotion/
                                 tab/soap/...) disagrees with the matched product's
                                 form-group (e.g. XEPIBACT CREAM -> Xepibact Tablets).
                                 Uses a form-EQUIVALENCE map so oint==ointment,
                                 gel==emulgel, softgel==capsule, syrup==suspension
                                 do NOT false-flag.
  * pack-number-mismatch count — MATCHED rows whose raw size number (30gm/50ml)
                                 disagrees with the matched product's pack number.

Modes:
  python scripts/validate_master_coverage.py                 # regression manifest globs
  python scripts/validate_master_coverage.py --final-data    # full corpus (shared cache)
  python scripts/validate_master_coverage.py --final-data --workers 12
"""
import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if os.path.join(ROOT, "scripts") not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "scripts"))

# ---- form + size classification ----
# Use the MATCHER's own form-group logic (single source of truth) so the oracle's
# form-mismatch count matches exactly what core.product_master._form_correct gates on.
from core.product_master import _form_groups as form_groups  # noqa: E402
_SIZE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(mls|ml|gms|gm|grams|gram|kg|ltr|g|l)\b", re.I)


def size_numbers(text):
    """Numeric magnitudes of size tokens (gm/g/ml folded, unit ignored)."""
    out = set()
    for m in _SIZE_RE.finditer(str(text or "")):
        n = m.group(1)
        if n.endswith(".0"):
            n = n[:-2]
        try:
            out.add(float(n))
        except ValueError:
            pass
    return out


def _accumulate(rows, stats, form_offenders, pack_offenders):
    """Update stats from one file's extracted rows."""
    for row in rows:
        if "product_name" not in row:
            continue
        # Empty product-name rows are structural/blank, not products to match — count
        # them separately (a data-quality signal) but keep them out of the match rate.
        if not str(row.get("product_name") or "").strip():
            stats["empty_name"] += 1
            continue
        stats["total"] += 1
        matched = "raw_product_name" in row
        if not matched:
            stats["unmatched"] += 1
            stats["unmatched_names"][str(row.get("product_name", ""))] += 1
            continue
        stats["matched"] += 1
        raw = str(row.get("raw_product_name") or "")
        canon = str(row.get("canonical_name") or row.get("product_name") or "")
        pack = str(row.get("pack") or "")
        # form mismatch (cross-group only)
        rg, cg = form_groups(raw), form_groups(canon)
        if rg and cg and not (rg & cg):
            stats["form_mismatch"] += 1
            form_offenders[(raw[:50], canon)] += 1
        # pack-number mismatch: raw states a size that disagrees with matched pack number
        rs = size_numbers(raw)
        ps = size_numbers(pack) or size_numbers(canon)
        if rs and ps and not (rs & ps):
            stats["pack_mismatch"] += 1
            pack_offenders[(raw[:50], canon, pack)] += 1


def _new_stats():
    return {"total": 0, "matched": 0, "unmatched": 0, "form_mismatch": 0,
            "pack_mismatch": 0, "empty_name": 0, "unmatched_names": Counter()}


def run_manifest():
    from extractors.party_pdf.pipeline import extract as ep_pdf
    from extractors.party_xlsx.pipeline import extract as ep_xlsx
    from extractors.stock_pdf.pipeline import extract as es_pdf
    from extractors.stock_xlsx.pipeline import extract as es_xlsx
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "regression_test", os.path.join(os.path.dirname(__file__), "regression_test.py"))
    reg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reg)
    exts = {"party_pdf": ep_pdf, "party_xlsx": ep_xlsx, "stock_pdf": es_pdf, "stock_xlsx": es_xlsx}
    manifest = json.load(open(os.path.join(ROOT, "tests", "regression_manifest.json")))
    reports_root = r"D:\Devs\Reports\Data"
    stats, fo, po = _new_stats(), Counter(), Counter()
    for name, info in manifest.get("suites", {}).items():
        route = info.get("route")
        files = reg._resolve_glob(Path(reports_root), info.get("glob", "")) if info.get("glob") else []
        for fp in files:
            if not os.path.exists(fp):
                continue
            try:
                res = exts[route](open(fp, "rb").read())
            except Exception:
                continue
            _accumulate(res.get("rows", []), stats, fo, po)
    return stats, fo, po


def run_final_data(workers):
    import run_batch as rb
    import batch_extract as be
    fd = Path(r"D:\Devs\Reports\Final_Data")
    jobs = list(rb.discover_folder(fd))
    print(f"Final_Data jobs: {len(jobs)} (filling cache with {workers} workers)")
    for i in range(0, len(jobs), 400):
        be.extract_batch(jobs[i:i + 400], workers=workers, progress=False)
    stats, fo, po = _new_stats(), Counter(), Counter()
    for route, path in jobs:
        try:
            res = be.get(route, str(path))
        except Exception:
            continue
        if res.get("_extract_error"):
            continue
        _accumulate(res.get("rows", []), stats, fo, po)
    return stats, fo, po


def main():
    ap = argparse.ArgumentParser(description="Master-coverage + accuracy oracle")
    ap.add_argument("--final-data", action="store_true", help="Run over the full Final_Data corpus (shared cache)")
    ap.add_argument("--workers", type=int, default=12)
    args = ap.parse_args()

    stats, form_off, pack_off = run_final_data(args.workers) if args.final_data else run_manifest()

    t = stats["total"] or 1
    print("\n=== Accuracy Oracle ===")
    print(f"Named product rows:        {stats['total']}   (empty-name rows excluded: {stats['empty_name']})")
    print(f"Matched to master:         {stats['matched']}  ({100*stats['matched']/t:.1f}%)")
    print(f"Unmatched:                 {stats['unmatched']}  ({100*stats['unmatched']/t:.1f}%)")
    print(f"Form-mismatch (matched):   {stats['form_mismatch']}  (raw form-group != matched form-group)")
    print(f"Pack-number-mismatch:      {stats['pack_mismatch']}  (raw size != matched pack)")

    if form_off:
        print(f"\nTop form-mismatches ({len(form_off)} distinct):")
        for (raw, canon), n in form_off.most_common(15):
            print(f"  {n:4}  {raw!r} -> {canon!r}")
    if pack_off:
        print(f"\nTop pack-mismatches ({len(pack_off)} distinct):")
        for (raw, canon, pack), n in pack_off.most_common(15):
            print(f"  {n:4}  {raw!r} -> {canon!r} [{pack}]")
    if stats["unmatched_names"]:
        print(f"\nTop unmatched names ({len(stats['unmatched_names'])} distinct):")
        for name, n in stats["unmatched_names"].most_common(20):
            print(f"  {n:4}  {name!r}")


if __name__ == "__main__":
    main()
