"""Comprehensive triage: parse the full-regression output for every FAIL, then for
each failing file diff enrichment under the clean C0 (5462) vs the current catalog.
  - VANISHED product (in C0, gone now)  => a COLLAPSE: find the new synonym that
    captured its raw and mark it for removal.
  - APPEARED-only (no vanish, count same/up, raw->canonical) => an IMPROVEMENT: keep.
Outputs the exact culprit-synonym removal set (per product) -> _triage_remove.json
and a human summary. Re-extracts only the failing files (fast subset)."""
import json, copy, sys, re
from pathlib import Path
from difflib import SequenceMatcher
sys.path.insert(0, ".")
import build_product_synonyms as B
import core.product_master as PM
from core.product_master import _normalize_name as N
from extractors import party_pdf, party_xlsx, stock_pdf, stock_xlsx

ROUTES = {"party_pdf":party_pdf.extract,"party_xlsx":party_xlsx.extract,
          "stock_pdf":stock_pdf.extract,"stock_xlsx":stock_xlsx.extract}
MAN = json.load(open("tests/regression_manifest.json", encoding="utf-8"))
REPORTS = Path(MAN.get("reports_root", "D:/Devs/Reports/Data"))
SUITE_ROUTE = {name: cfg["route"] for name, cfg in MAN["suites"].items()} if "suites" in MAN \
              else {name: cfg["route"] for name, cfg in MAN.items() if isinstance(cfg, dict) and "route" in cfg}

CUR = json.load(open("data/product_master.json", encoding="utf-8"))
safe_added = json.load(open("scripts/_safe_added.json", encoding="utf-8"))
new_syns = {s for v in safe_added.values() for s in v}

# rebuild clean C0 in memory
base_by_canon = {p.get("canonical_name"): p for p in json.load(open(
    r"C:\Users\Sandeep\Downloads\KLM\stock-backends\data\product_master.json", encoding="utf-8"))}
C0 = copy.deepcopy(CUR)
for p in C0:
    b = base_by_canon.get(p.get("canonical_name"))
    p["synonyms"] = list(b.get("synonyms", [])) if b else []
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
assert sum(len(p.get("synonyms",[])) for p in C0)==5462, "C0 rebuild != 5462"

# parse FAIL files + their suite/route from the regression log
fails = []   # (route, filename)
cur_route = None
for line in open("scripts/_full_regression.txt", encoding="utf-8", errors="ignore"):
    m = re.match(r"\[(.+?)\]\s*$", line.strip())
    if m: cur_route = SUITE_ROUTE.get(m.group(1)); continue
    m = re.match(r"\s*FAIL (.+)$", line.rstrip())
    if m and cur_route: fails.append((cur_route, m.group(1).strip()))

allf = {p.name: p for p in REPORTS.rglob("*") if p.is_file()}
def rt(nr, cand):
    nc=N(cand)
    if not nc: return 0.0
    if nr==nc: return 1.0
    if (nc in nr or nr in nc) and len(nc)>=4: return 0.90
    return SequenceMatcher(None,nr,nc).ratio()
def enrich_sets(catalog, route, path):
    PM._PRODUCT_MASTER = catalog
    res = ROUTES[route](path.read_bytes(), {"filename": path.name})
    byc={}
    for r in res.get("rows") or []:
        raw=r.get("raw_product_name") or r.get("product_name"); canon=r.get("product_name")
        if raw is not None: byc.setdefault(canon,set()).add(raw)
    return byc

remove = {}        # wrong_canonical -> set(culprit new synonyms)
improvements=[]; collapses=[]
for route, fn in fails:
    p = allf.get(fn)
    if not p: print(f"?? not found: {fn}"); continue
    a = enrich_sets(C0, route, p); b = enrich_sets(CUR, route, p)
    vanished = set(a)-set(b); appeared = set(b)-set(a)
    if not vanished:
        if appeared: improvements.append((fn, sorted(appeared)))
        continue
    PM._PRODUCT_MASTER = CUR
    for v in vanished:
        for raw in sorted(a[v]):
            mm = PM.normalize_product(raw); now = mm.get("canonical_name") if mm else None
            if now != v and now is not None:
                # culprit = highest-scoring NEW synonym under `now` for this raw
                P = next(pp for pp in CUR if pp.get("canonical_name")==now)
                cand = sorted(((rt(N(raw), s), s) for s in P.get("synonyms",[]) if s in new_syns), reverse=True)
                if cand and cand[0][0] >= 0.90:
                    remove.setdefault(now, set()).add(cand[0][1])
                    collapses.append((fn, raw, v, now, cand[0][1]))

print(f"FAIL files analysed: {len(fails)}")
print(f"COLLAPSES (to fix): {len(collapses)}   IMPROVEMENTS (keep): {len(improvements)}")
print("\n--- collapses & culprits ---")
for fn,raw,was,now,syn in collapses:
    print(f"  {fn}: {raw!r}  {was!r} -> {now!r}   culprit {syn!r}")
print("\n--- improvements (kept) ---")
for fn,app in improvements:
    print(f"  {fn}: +{app}")
out = {c: sorted(s) for c,s in remove.items()}
json.dump(out, open("scripts/_triage_remove.json","w",encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"\n{sum(len(v) for v in out.values())} culprit synonyms across {len(out)} products -> scripts/_triage_remove.json")
