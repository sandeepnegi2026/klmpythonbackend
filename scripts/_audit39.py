"""For every FAIL in _full_regression3.txt, decide whether it's MINE (caused by the
new synonyms) or PRE-EXISTING, by snapshotting each file under the clean C0 (5462)
AND the current catalog and comparing both to the stored baseline.

  C0==baseline & CUR!=baseline -> MINE (synonyms changed it) -> regression or improvement
  C0!=baseline & CUR!=baseline -> PRE-EXISTING (baseline stale even vs clean C0)
  C0!=baseline & CUR==baseline -> MINE-FIXED (synonyms fixed a pre-existing fail)
"""
import json, copy, sys, re
from pathlib import Path
sys.path.insert(0, ".")
import build_product_synonyms as B
import core.product_master as PM
from core.product_master import _normalize_name as N
import regression_test as RT

CUR = json.load(open("data/product_master.json", encoding="utf-8"))
base_by_canon = {p.get("canonical_name"): p for p in json.load(open(
    r"C:\Users\Sandeep\Downloads\KLM\stock-backends\data\product_master.json", encoding="utf-8"))}
C0 = copy.deepcopy(CUR)
for p in C0:
    b = base_by_canon.get(p.get("canonical_name")); p["synonyms"] = list(b.get("synonyms", [])) if b else []
def _apply(cat, sp):
    cov=set()
    for p in cat:
        cov.add(N(p.get("canonical_name","")))
        for s in p.get("synonyms",[]): cov.add(N(s))
    cov.discard("")
    idx=B._build_index(cat)
    for s in sorted(sp):
        n=N(s)
        if not n or n in cov or not B._is_plausible_product(s,n): continue
        pr=B._strict_match(n,idx,0.90,0.03)
        if pr is not None: pr.setdefault("synonyms",[]).append(s); cov.add(n)
_apply(C0, json.load(open("scripts/_synonym_spellings_cache_26june.json",encoding="utf-8"))["spellings"])
assert sum(len(p.get("synonyms",[])) for p in C0)==5462

MAN = RT._load_manifest()
SUITE_ROUTE = {n: c["route"] for n,c in (MAN.get("suites", MAN)).items() if isinstance(c, dict) and "route" in c}
REPORTS = Path(MAN.get("reports_root", "D:/Devs/Reports/Data"))
allf = {p.name: p for p in REPORTS.rglob("*") if p.is_file()}
BL = Path("tests/baselines")

# parse fails + suite
fails=[]; suite=None
for line in open("scripts/_full_regression3.txt", encoding="utf-8", errors="ignore"):
    m=re.match(r"\[(.+?)\]\s*$", line.strip())
    if m: suite=m.group(1); continue
    m=re.match(r"\s*FAIL (.+)$", line.rstrip())
    if m: fails.append((suite, m.group(1).strip()))

def snap(cat, route, p):
    PM._PRODUCT_MASTER = cat
    return RT._snapshot(route, p)

mine=[]; pre=[]; fixed=[]; missing=[]
for suite, fn in fails:
    p = allf.get(fn)
    blp = BL / suite / f"{fn}.json"
    if not p or not blp.exists():
        missing.append(fn); continue
    bl = json.load(open(blp, encoding="utf-8")); route = bl["route"]
    d0 = RT._compare(bl, snap(C0, route, p))
    dc = RT._compare(bl, snap(CUR, route, p))
    if not d0 and dc:    mine.append((fn, dc))
    elif d0 and not dc:  fixed.append(fn)
    elif d0 and dc:      pre.append(fn)
    # (not d0 and not dc) impossible since it's in fail list under CUR
print(f"FAILS analysed: {len(fails)}  (missing baseline/file: {len(missing)})")
print(f"  PRE-EXISTING (fail under clean C0 too, NOT mine): {len(pre)}")
print(f"  MINE-FIXED (synonyms fixed a pre-existing fail):  {len(fixed)}")
print(f"  MINE (synonyms changed it):                       {len(mine)}")
print("\n=== MINE (need review) ===")
for fn, dc in mine:
    print(f"  {fn}")
    for d in dc: print(f"      - {d}")
