"""In-memory experiment: can we deterministically reproduce the clean 5462-synonym
catalog from a canonical-only base + the three known-good 26-June spelling caches,
using the tool's OWN matching functions? Touches NO live files."""
import json, copy, sys
sys.path.insert(0, ".")
import build_product_synonyms as B
from core.product_master import _normalize_name as N

CUR = json.load(open("../data/product_master.json", encoding="utf-8"))

def base_from(catalog):
    base = copy.deepcopy(catalog)
    for p in base:
        p["synonyms"] = []
    return base

def load_cache(fn):
    return json.load(open(fn, encoding="utf-8"))["spellings"]

def apply_cache(catalog, spellings, min_score=0.90, margin=0.03):
    """Replicate build_product_synonyms.main()'s match+add loop exactly."""
    covered = set()
    for p in catalog:
        covered.add(N(p.get("canonical_name", "")))
        for s in p.get("synonyms", []):
            covered.add(N(s))
    covered.discard("")
    index = B._build_index(catalog)
    added = 0
    for spelling in sorted(spellings):
        norm = N(spelling)
        if not norm or norm in covered:
            continue
        if not B._is_plausible_product(spelling, norm):
            continue
        prod = B._strict_match(norm, index, min_score, margin)
        if prod is not None:
            prod.setdefault("synonyms", []).append(spelling)
            covered.add(norm)
            added += 1
    return added

good = ["_synonym_spellings_cache_26june.json",
        "_synonym_spellings_cache.json",
        "_synonym_spellings_cache_fullcorpus.json"]

cat = base_from(CUR)
print(f"base synonyms = {sum(len(p['synonyms']) for p in cat)} (should be 0)")
for fn in good:
    sp = load_cache(fn)
    n = apply_cache(cat, sp)
    tot = sum(len(p.get('synonyms', [])) for p in cat)
    print(f"  applied {fn} ({len(sp)} spellings): +{n} -> total {tot}")
final = sum(len(p.get('synonyms', [])) for p in cat)
print(f"\nREBUILT synonyms = {final}   target 5462   diff = {final-5462}")
