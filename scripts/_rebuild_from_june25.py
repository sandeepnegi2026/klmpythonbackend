"""Decisive test: reproduce the clean 5462-synonym catalog deterministically by
starting from the June-25 backup (2729 synonyms) and re-applying the three
known-good 26-June spelling caches with the tool's own matching. If this lands at
~5462, it's our clean C0 to rebuild from."""
import json, copy, sys
sys.path.insert(0, ".")
import build_product_synonyms as B
from core.product_master import _normalize_name as N

JUNE25 = r"C:\Users\Sandeep\Downloads\KLM\stock-backends\data\product_master.json"
CUR    = "../data/product_master.json"   # for canonical/pack identity (303 products, stable)

base = json.load(open(JUNE25, encoding="utf-8"))
cur  = json.load(open(CUR, encoding="utf-8"))
print(f"June25 base: {len(base)} products, {sum(len(p.get('synonyms',[])) for p in base)} synonyms")
print(f"current:     {len(cur)} products")

# Align: June25 may have a different product set than current (303). Map by canonical_name.
cur_by_canon = {p.get("canonical_name"): p for p in cur}
base_by_canon = {p.get("canonical_name"): p for p in base}
print(f"canon overlap: {len(set(cur_by_canon) & set(base_by_canon))} / cur {len(cur_by_canon)} / base {len(base_by_canon)}")

def apply_cache(catalog, spellings, min_score=0.90, margin=0.03):
    covered = set()
    for p in catalog:
        covered.add(N(p.get("canonical_name","")))
        for s in p.get("synonyms",[]): covered.add(N(s))
    covered.discard("")
    index = B._build_index(catalog)
    added = 0
    for spelling in sorted(spellings):
        norm = N(spelling)
        if not norm or norm in covered: continue
        if not B._is_plausible_product(spelling, norm): continue
        prod = B._strict_match(norm, index, min_score, margin)
        if prod is not None:
            prod.setdefault("synonyms", []).append(spelling)
            covered.add(norm); added += 1
    return added

# Use the CURRENT product list (303) as the catalog skeleton, but seed synonyms from June25.
cat = copy.deepcopy(cur)
for p in cat:
    b = base_by_canon.get(p.get("canonical_name"))
    p["synonyms"] = list(b.get("synonyms", [])) if b else []
print(f"\nseeded-from-June25 onto current skeleton: {sum(len(p['synonyms']) for p in cat)} synonyms")

for fn in ["_synonym_spellings_cache_26june.json","_synonym_spellings_cache.json","_synonym_spellings_cache_fullcorpus.json"]:
    sp = json.load(open(fn, encoding="utf-8"))["spellings"]
    n = apply_cache(cat, sp)
    print(f"  +{fn}: +{n} -> {sum(len(p.get('synonyms',[])) for p in cat)}")
print(f"\nREBUILT = {sum(len(p.get('synonyms',[])) for p in cat)}   target 5462")
