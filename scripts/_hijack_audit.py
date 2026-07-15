"""Static, comprehensive hijack audit (no extraction, fast).

Replays the RUNTIME matcher (core.product_master.normalize_product, min_score 0.85,
containment bonus) over EVERY known product spelling (26-June corpus + the four new
folders = real raws) under the clean C0 (5462) vs the current catalog. For any
spelling whose enriched product CHANGES:
  * C0 matched a product, current matches a DIFFERENT one  -> REGRESSION (a new
    synonym hijacked it). Record the culprit new synonym for removal.
  * C0 matched nothing, current matches something          -> IMPROVEMENT (keep).
This covers all products, not just the regression sample files.

--apply removes the culprit synonyms from both mirrors.
"""
import json, copy, sys
from difflib import SequenceMatcher
sys.path.insert(0, ".")
import build_product_synonyms as B
import core.product_master as PM
from core.product_master import _normalize_name as N

APPLY = "--apply" in sys.argv
MIRRORS = ["data/product_master.json", "../Backends/data/product_master.json"]
CUR = json.load(open(MIRRORS[0], encoding="utf-8"))
safe_added = json.load(open("scripts/_safe_added.json", encoding="utf-8"))
new_syns = {s for v in safe_added.values() for s in v}

# clean C0 (5462)
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
assert sum(len(p.get("synonyms",[])) for p in C0)==5462, "C0 != 5462"

# all known real spellings
known = set()
for fn in ["_synonym_spellings_cache_26june.json","_synonym_spellings_cache.json",
           "_synonym_spellings_cache_fullcorpus.json","_hb_merged.json"]:
    known |= set(json.load(open("scripts/"+fn, encoding="utf-8"))["spellings"].keys())
print(f"auditing {len(known)} distinct known spellings")

def match(catalog, raw):
    PM._PRODUCT_MASTER = catalog
    return PM.normalize_product(raw)
def canon(m): return m.get("canonical_name") if m else None
def rt(nr, cand):
    nc=N(cand)
    if not nc: return 0.0
    if nr==nc: return 1.0
    if (nc in nr or nr in nc) and len(nc)>=4: return 0.90
    return SequenceMatcher(None,nr,nc).ratio()

remove = {}     # wrong canonical -> set(new synonyms)
regress=[]; improve=0
for raw in known:
    q = canon(match(C0, raw)); p = canon(match(CUR, raw))
    if p == q: continue
    if q is None:
        improve += 1; continue          # was unmatched, now matched = improvement
    if p is None:
        continue                          # was matched, now unmatched (shouldn't happen on additions)
    # raw moved q -> p : a new synonym under p hijacked it
    P = next(pp for pp in CUR if pp.get("canonical_name")==p)
    cand = sorted(((rt(N(raw), s), s) for s in P.get("synonyms",[]) if s in new_syns), reverse=True)
    if cand and cand[0][0] >= 0.85:
        remove.setdefault(p, set()).add(cand[0][1])
        regress.append((raw, q, p, cand[0][1]))

print(f"REGRESSIONS (raw moved to wrong product): {len(regress)}")
print(f"IMPROVEMENTS (newly matched): {improve}")
print(f"distinct culprit new synonyms: {sum(len(v) for v in remove.values())}")
print("\n--- sample regressions ---")
for raw,q,p,syn in regress[:40]:
    print(f"  {raw!r}: {q!r} -> {p!r}  culprit {syn!r}")
json.dump({c:sorted(s) for c,s in remove.items()}, open("scripts/_hijack_remove.json","w",encoding="utf-8"), ensure_ascii=False, indent=2)

if APPLY and remove:
    allrm = {s for v in remove.values() for s in v}
    n=0
    for p in CUR:
        before=len(p.get("synonyms",[]))
        p["synonyms"]=[s for s in p.get("synonyms",[]) if not (p.get("canonical_name") in remove and s in remove[p["canonical_name"]])]
        n+=before-len(p["synonyms"])
    payload=json.dumps(CUR,indent=2,ensure_ascii=False)+"\n"
    for m in MIRRORS: open(m,"w",encoding="utf-8").write(payload)
    print(f"\nremoved {n} culprit synonyms -> both mirrors, total {sum(len(p.get('synonyms',[])) for p in CUR)}")
