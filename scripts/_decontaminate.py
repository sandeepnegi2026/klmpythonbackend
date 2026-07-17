"""Detect & strip cross-variant contaminated synonyms in product_master.json.

Precise contamination rule (root cause of the regression): a synonym filed under
host product P is contamination iff it asserts a discriminating attribute that P's
own IDENTITY (canonical_name + pack) lacks BUT a same-brand SIBLING product owns:
  * a strength/pack NUMBER (e.g. a 100ML spelling filed under the 60ML product), or
  * a VARIANT marker token (m, forte, plus, sr, ds, od, xt, cv, lb, intense ...)
    e.g. 'HISTABILL M' filed under the plain 'Histabil Tablet' while a sibling
    'Histabil M Tablets' exists.
Such a synonym makes two distinct sibling variants collapse onto one canonical ->
wrong product_count / sample_products. We do NOT flag a stray number/token with no
sibling owner (harmless extra specificity), keeping removal conservative.

Report (default) or --apply (strip flagged synonyms from BOTH mirrors).
"""
import json, sys, re
from collections import defaultdict, Counter
sys.path.insert(0, ".")
import build_product_synonyms as B
from core.product_master import _normalize_name as N

APPLY = "--apply" in sys.argv
MIRRORS = ["../data/product_master.json",
           "../../Backends/data/product_master.json"]
CUR = json.load(open(MIRRORS[0], encoding="utf-8"))
merged = set(json.load(open("_hb_merged.json", encoding="utf-8"))["spellings"].keys())

VARIANT_TOKENS = {
    "m","md","mf","ds","sr","xt","od","cv","lb","forte","plus","active","total","intense",
}
# Strength/size numbers only: drop pack MULTIPLIERS ('1*30', '10*50' -> the leading
# count) and the bare unit-count '1', which are not discriminating between siblings.
_MULT = re.compile(r"\b\d+\s*\*")
def nums(s):
    s = _MULT.sub(" ", s)              # remove 'N*' multiplier prefixes
    out = set(re.findall(r"\d+", s))
    out.discard("1")                   # bare single-unit count, never a strength
    return out

def identity(p):
    """Stable identity = canonical_name + pack only (NOT synonyms)."""
    parts = [N(p.get("canonical_name","")), N(str(p.get("pack","")))]
    inum, itok = set(), set()
    for n in parts:
        inum |= nums(n); itok |= set(n.split())
    inum |= nums(str(p.get("pack","")))
    return inum, itok

# brand -> list of (product, idnums, idtoks)
by_brand = defaultdict(list)
ident = {}
for p in CUR:
    inum, itok = identity(p)
    ident[id(p)] = (inum, itok)
    brand = B._brand_token(N(p.get("canonical_name","")))
    by_brand[brand].append(p)

# Per-product: fraction of synonyms whose norm carries a given number. A number
# present in a LARGE share of the host's synonyms is the host's OWN strength (its
# canonical may omit it, e.g. 'Imxia F' = 5%), so it must NOT be treated as foreign.
def host_num_share(p):
    syns = p.get("synonyms", [])
    if not syns: return {}
    cnt = defaultdict(int)
    for s in syns:
        for x in nums(N(s)): cnt[x] += 1
    return {x: c/len(syns) for x, c in cnt.items()}
NUM_SHARE = {id(p): host_num_share(p) for p in CUR}
OWN_SHARE = 0.30   # >=30% of synonyms carry it -> it's the host's own strength

def sibling_owns_num(p, num):
    if NUM_SHARE[id(p)].get(num, 0) >= OWN_SHARE:
        return None                      # host's own strength, not foreign
    brand = B._brand_token(N(p.get("canonical_name","")))
    for q in by_brand[brand]:
        if q is p: continue
        if num in ident[id(q)][0]: return q.get("canonical_name")
    return None

def sibling_owns_tok(p, tok):
    brand = B._brand_token(N(p.get("canonical_name","")))
    for q in by_brand[brand]:
        if q is p: continue
        if tok in ident[id(q)][1]: return q.get("canonical_name")
    return None

flagged = []  # (canon, synonym, reason, is_new)
for p in CUR:
    inum, itok = ident[id(p)]
    canon = p.get("canonical_name")
    for s in p.get("synonyms", []):
        norm = N(s)
        reason = None
        for num in sorted(nums(norm) - inum):
            owner = sibling_owns_num(p, num)
            if owner:
                reason = f"strength/pack {num} -> sibling {owner!r}"; break
        if not reason:
            for tok in sorted((set(norm.split()) & VARIANT_TOKENS) - itok):
                owner = sibling_owns_tok(p, tok)
                if owner:
                    reason = f"variant {tok!r} -> sibling {owner!r}"; break
        if reason:
            flagged.append((canon, s, reason, s in merged))

new_f = [f for f in flagged if f[3]]
old_f = [f for f in flagged if not f[3]]
print(f"FLAGGED contaminated synonyms: {len(flagged)}  (new/merged={len(new_f)}, pre-existing={len(old_f)})")
print("kinds:", dict(Counter("number" if "strength" in r else "variant" for _,_,r,_ in flagged)))
print("\n--- variant flags (HISTABILL M class) ---")
for c,s,r,isnew in [f for f in flagged if "variant" in f[2]][:30]:
    print(f"  [{'NEW' if isnew else 'old'}] {s!r}  under {c!r}  -- {r}")
print("\n--- number flags (first 30) ---")
for c,s,r,isnew in [f for f in flagged if "strength" in f[2]][:30]:
    print(f"  [{'NEW' if isnew else 'old'}] {s!r}  under {c!r}  -- {r}")

json.dump(flagged, open("_flagged_contam.json","w",encoding="utf-8"), ensure_ascii=False, indent=2)

if APPLY:
    flag_set = defaultdict(set)
    for c,s,r,isnew in flagged: flag_set[c].add(s)
    removed = 0
    for p in CUR:
        c = p.get("canonical_name")
        if c in flag_set:
            before = len(p.get("synonyms",[]))
            p["synonyms"] = [s for s in p["synonyms"] if s not in flag_set[c]]
            removed += before - len(p["synonyms"])
    payload = json.dumps(CUR, indent=2, ensure_ascii=False) + "\n"
    for m in MIRRORS:
        open(m,"w",encoding="utf-8").write(payload)
    tot = sum(len(p.get('synonyms',[])) for p in CUR)
    print(f"\nAPPLIED: removed {removed} contaminated synonyms from both mirrors -> {tot} synonyms")
