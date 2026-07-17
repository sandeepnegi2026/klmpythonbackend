"""Re-add new product synonyms from _hb_merged onto the CLEAN C0 (5462) catalog,
but only the SAFE ones: a spelling is attached to harvest-matched product P only
if it survives four guards that block the contamination classes proven to break
runtime enrichment (collapsing distinct sibling products):

  G1 strength/pack-number: S carries a number P's identity lacks but a same-brand
     sibling owns  (e.g. a 100ML spelling under the 60ML product).
  G2 variant token:        S carries a variant marker (m/ds/sr/forte/plus/xl/...)
     P lacks but a sibling owns  (e.g. 'HISTABILL M' under plain Histabil).
  G3 dosage form:          S's dosage form disjoint from P's
     (e.g. 'SOFIDEW BABY LOTION' / '...SHAMPOO' under '...MASSAGE OIL', or a
      TABLET spelling under a SUSPENSION product).
  G4 sibling collision:    under the loose RUNTIME matcher, a same-brand sibling
     scores >= P for S  (catches bare-brand generics like 'LULIZOL' under XL).

Writes both mirrors (dry-run unless --apply). Reports added vs rejected-by-guard.
"""
import json, copy, sys, re
from collections import defaultdict
from difflib import SequenceMatcher
sys.path.insert(0, ".")
import build_product_synonyms as B
from core.product_master import _normalize_name as N

APPLY = "--apply" in sys.argv
MIRRORS = ["../data/product_master.json", "../../Backends/data/product_master.json"]
CAT = json.load(open(MIRRORS[0], encoding="utf-8"))   # clean C0 = 5462
assert sum(len(p.get("synonyms",[])) for p in CAT) == 5462, "base is not the clean 5462 C0!"

merged = json.load(open("_hb_merged.json", encoding="utf-8"))["spellings"]

VARIANT = {"m","md","mf","ds","sr","xt","od","cv","lb","xl","nf","ax","es","dx","kid",
           "forte","plus","active","total","intense","gold","max","ultra","nxt","aha"}
# Dosage-form families: each maps to a canonical family id so abbreviations
# ('oint'=='ointment', 'tab'=='tablet'=='tablets') are treated as the SAME form
# and only genuinely different forms (lotion vs oil) trip G3.
FORM_FAMILY = {}
for fam, words in {
    "gel": ["gel","emulgel"], "cream": ["cream","crm"], "lotion": ["lotion","lot"],
    "oil": ["oil"], "soap": ["soap"], "syrup": ["syrup","syp","sirup","syr"],
    "suspension": ["suspension","susp","suspn","suspention"], "drops": ["drops","drop"],
    "tablet": ["tablet","tablets","tab","tabs","dt"], "capsule": ["capsule","capsules","cap","caps","capsuls"],
    "ointment": ["ointment","oint"," oint","iontment"], "solution": ["solution","sol","soln","solu"],
    "powder": ["powder","pow","pwd"], "spray": ["spray"], "shampoo": ["shampoo","shmp"],
    "wash": ["wash","facewash"], "serum": ["serum"], "kit": ["kit"],
    "sachet": ["sachet","sachets"], "gummy": ["gummy"], "sunscreen": ["sunscreen"],
    "massage": ["massage"], "dusting": ["dusting"], "lozenges": ["lozenges","loz"],
}.items():
    for w in words: FORM_FAMILY[w] = fam
FORM = set(FORM_FAMILY)
_MULT = re.compile(r"\b\d+\s*\*")
def nums(s):
    s = _MULT.sub(" ", s); out = set(re.findall(r"\d+", s)); out.discard("1"); return out

def identity(p):
    parts = [N(p.get("canonical_name","")), N(str(p.get("pack","")))]
    inum, itok = set(), set()
    for n in parts: inum |= nums(n); itok |= set(n.split())
    inum |= nums(str(p.get("pack","")))
    return inum, itok

by_brand = defaultdict(list); IDENT = {}
for p in CAT:
    IDENT[id(p)] = identity(p)
    by_brand[B._brand_token(N(p.get("canonical_name","")))].append(p)

def rt_score(norm, prod):
    """Runtime-matcher score of norm vs a product's candidates (containment-aware)."""
    best = 0.0
    for cand in [prod.get("canonical_name","")] + prod.get("synonyms",[]):
        nc = N(cand)
        if not nc: continue
        if norm == nc: return 1.0
        if (nc in norm or norm in nc) and len(nc) >= 4: sc = 0.90
        else: sc = SequenceMatcher(None, norm, nc).ratio()
        if sc > best: best = sc
    return best

def guards(s, P):
    """Return reason string if S must be REJECTED for product P, else None."""
    norm = N(s); st = set(norm.split()); sn = nums(norm)
    inum, itok = IDENT[id(P)]
    brand = B._brand_token(N(P.get("canonical_name","")))
    sibs = [q for q in by_brand[brand] if q is not P]
    # G1 number
    for num in sorted(sn - inum):
        if any(num in IDENT[id(q)][0] for q in sibs):
            return f"G1 number {num}"
    # G2 variant token
    for tok in sorted((st & VARIANT) - itok):
        if any(tok in IDENT[id(q)][1] for q in sibs):
            return f"G2 variant {tok!r}"
    # G3 dosage form mismatch (compare FAMILIES, so 'oint'=='ointment', 'tab'=='tablet')
    sfam = {FORM_FAMILY[t] for t in st & FORM}
    pfam = {FORM_FAMILY[t] for t in itok & FORM}
    if sfam and pfam and not (sfam & pfam):
        return f"G3 form {sorted(sfam)} vs P {sorted(pfam)}"
    # G4 sibling collision under runtime matcher
    sP = rt_score(norm, P)
    if any(rt_score(norm, q) >= sP for q in sibs):
        return "G4 sibling-collision"
    return None

# covered set = clean C0
covered = set()
for p in CAT:
    covered.add(N(p.get("canonical_name","")))
    for s in p.get("synonyms",[]): covered.add(N(s))
covered.discard("")
index = B._build_index(CAT)

added = defaultdict(list); rejected = defaultdict(list); unmatched = 0
for s in sorted(merged):
    norm = N(s)
    if not norm or norm in covered: continue
    if not B._is_plausible_product(s, norm): continue
    P = B._strict_match(norm, index, 0.90, 0.03)
    if P is None:
        unmatched += 1; continue
    reason = guards(s, P)
    if reason:
        rejected[reason.split()[0]].append((s, P.get("canonical_name"), reason))
    else:
        P.setdefault("synonyms", []).append(s); covered.add(norm)
        added[P.get("canonical_name")].append(s)

n_add = sum(len(v) for v in added.values())
n_rej = sum(len(v) for v in rejected.values())
print(f"SAFE additions: {n_add} across {len(added)} products")
print(f"REJECTED by guard: {n_rej}   unmatched(no product): {unmatched}")
for g in sorted(rejected): print(f"   {g}: {len(rejected[g])}")
print("\nsample rejects:")
for g in sorted(rejected):
    for s,c,r in rejected[g][:4]:
        print(f"   [{r}] {s!r} -> would-be {c!r}")
json.dump({k:v for k,v in added.items()}, open("_safe_added.json","w",encoding="utf-8"), ensure_ascii=False, indent=2)
json.dump([list(t) for v in rejected.values() for t in v], open("_safe_rejected.json","w",encoding="utf-8"), ensure_ascii=False, indent=2)

if APPLY and n_add:
    for p in CAT:
        seen, dd = set(), []
        for s in p.get("synonyms",[]):
            k = s.strip().lower()
            if k and k not in seen: seen.add(k); dd.append(s)
        p["synonyms"] = sorted(dd, key=str.lower)
    payload = json.dumps(CAT, indent=2, ensure_ascii=False) + "\n"
    for m in MIRRORS: open(m,"w",encoding="utf-8").write(payload)
    print(f"\nAPPLIED -> both mirrors, total synonyms now {sum(len(p.get('synonyms',[])) for p in CAT)}")
else:
    print("\nDRY RUN — nothing written (add --apply).")
