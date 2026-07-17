"""Restore the clean 5462-synonym catalog (C0) deterministically:
  June-25 backup synonyms  +  _synonym_spellings_cache_26june.json
applied with the harvest tool's own matcher and finalization (case-insensitive
dedup + sort), written to BOTH mirrors. Verified by regression afterwards.
"""
import json, copy, sys
sys.path.insert(0, ".")
import build_product_synonyms as B
from core.product_master import _normalize_name as N

JUNE25 = r"C:\Users\Sandeep\Downloads\KLM\stock-backends\data\product_master.json"
MIRRORS = ["../data/product_master.json", "../../Backends/data/product_master.json"]

base = json.load(open(JUNE25, encoding="utf-8"))
cur  = json.load(open(MIRRORS[0], encoding="utf-8"))
base_by_canon = {p.get("canonical_name"): p for p in base}

# current skeleton (303 products, stable canonical/code/pack/division), seed synonyms from June25
cat = copy.deepcopy(cur)
for p in cat:
    b = base_by_canon.get(p.get("canonical_name"))
    p["synonyms"] = list(b.get("synonyms", [])) if b else []

def apply_cache(catalog, spellings, min_score=0.90, margin=0.03):
    covered = set()
    for p in catalog:
        covered.add(N(p.get("canonical_name","")))
        for s in p.get("synonyms",[]): covered.add(N(s))
    covered.discard("")
    index = B._build_index(catalog)
    for spelling in sorted(spellings):
        norm = N(spelling)
        if not norm or norm in covered: continue
        if not B._is_plausible_product(spelling, norm): continue
        prod = B._strict_match(norm, index, min_score, margin)
        if prod is not None:
            prod.setdefault("synonyms", []).append(spelling)
            covered.add(norm)

sp = json.load(open("_synonym_spellings_cache_26june.json", encoding="utf-8"))["spellings"]
apply_cache(cat, sp)

# finalize exactly like build_product_synonyms.main(): dedup (case-insensitive) + sort
for p in cat:
    seen, deduped = set(), []
    for s in p.get("synonyms", []):
        k = s.strip().lower()
        if k and k not in seen:
            seen.add(k); deduped.append(s)
    p["synonyms"] = sorted(deduped, key=str.lower)

tot = sum(len(p.get("synonyms", [])) for p in cat)
print(f"restored synonyms = {tot}  (target 5462)")
if tot != 5462:
    print("!! count mismatch — NOT writing"); sys.exit(1)

payload = json.dumps(cat, indent=2, ensure_ascii=False) + "\n"
for m in MIRRORS:
    open(m, "w", encoding="utf-8").write(payload)
print("wrote clean C0 to both mirrors")
