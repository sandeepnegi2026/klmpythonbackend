"""Targeted authoritative validation: re-extract specific files and compare their
metrics to the stored regression baselines (no slow glob). Pass file names on argv;
route + baseline are auto-located."""
import json, sys
from pathlib import Path
sys.path.insert(0, ".")
from extractors import party_pdf, party_xlsx, stock_pdf, stock_xlsx
import regression_test as RT

BL = Path("tests/baselines")
REPORTS = Path(json.load(open("tests/regression_manifest.json",encoding="utf-8")).get("reports_root","D:/Devs/Reports/Data"))
allf = {p.name: p for p in REPORTS.rglob("*") if p.is_file()}

files = sys.argv[1:]
ok = bad = 0
for fn in files:
    # locate baseline (any suite) to get route
    bls = list(BL.glob(f"*/{fn}.json"))
    if not bls:
        print(f"?? no baseline for {fn}"); continue
    bl = json.load(open(bls[0], encoding="utf-8")); route = bl["route"]
    p = allf.get(fn)
    if not p:
        print(f"?? file not found {fn}"); continue
    actual = RT._snapshot(route, p)
    diffs = RT._compare(bl, actual)
    if diffs:
        bad += 1; print(f"FAIL {fn}")
        for d in diffs: print(f"     - {d}")
    else:
        ok += 1; print(f"OK   {fn}  (product_count={actual.get('product_count')})")
print(f"\n{ok} OK, {bad} FAIL")
