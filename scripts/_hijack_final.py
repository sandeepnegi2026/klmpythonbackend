"""Comprehensive convergent de-hijack (brand-bucketed = fast).

A NEW synonym S under product P is a COLLAPSE-causer iff there is a plausible
same-brand spelling T that, under the runtime matcher, S now wins (score >= T's
clean-C0 best score) BUT T already matched a DIFFERENT product Q!=P in C0. That is
exactly S stealing Q's row -> product collapse. Remove all such S. Synonyms that only
newly-match spellings unmatched in C0 (improvements) are KEPT.

Brand-bucketing keeps it to within-brand comparisons -> seconds. --apply writes both
mirrors."""
import json, copy, sys
from collections import defaultdict
from difflib import SequenceMatcher
sys.path.insert(0, ".")
import build_product_synonyms as B
from core.product_master import _normalize_name as N

APPLY = "--apply" in sys.argv
MIRRORS = ["data/product_master.json", "../Backends/data/product_master.json"]
CUR = json.load(open(MIRRORS[0], encoding="utf-8"))
safe_added = json.load(open("scripts/_safe_added.json", encoding="utf-8"))
new_syn_prod = {s: canon for canon, syns in safe_added.items() for s in syns}

# clean C0
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
assert sum(len(p.get("synonyms",[])) for p in C0)==5462

# plausible spellings
known=set()
for fn in ["_synonym_spellings_cache_26june.json","_synonym_spellings_cache.json",
           "_synonym_spellings_cache_fullcorpus.json","_hb_merged.json"]:
    known |= set(json.load(open("scripts/"+fn, encoding="utf-8"))["spellings"].keys())
known = [r for r in known if B._is_plausible_product(r, N(r))]

def brand(nr): return B._brand_token(nr)
def rt(nr,nc):
    if not nc: return 0.0
    if nr==nc: return 1.0
    if (nc in nr or nr in nc) and len(nc)>=4: return .9
    return SequenceMatcher(None,nr,nc).ratio()

# C0 index by brand: product -> (canon + synonym norms)
C0_by_brand = defaultdict(list)   # brand -> [(product_canonical, [cand_norms])]
for p in C0:
    cn = N(p.get("canonical_name",""))
    cands = [cn] + [N(s) for s in p.get("synonyms",[])]
    cands = [c for c in cands if c]
    C0_by_brand[brand(cn)].append((p.get("canonical_name"), cands))

# spellings bucketed by brand, with C0 best (product, score) precomputed
spell_by_brand = defaultdict(list)
for raw in known:
    nr = N(raw); spell_by_brand[brand(nr)].append((raw, nr))

def c0_best(nr, b):
    best=(None,0.0)
    for canon, cands in C0_by_brand.get(b, []):
        sc=max((rt(nr,c) for c in cands), default=0)
        if sc>best[1]: best=(canon,sc)
    return best if best[1]>=0.85 else (None, best[1])

# new synonyms bucketed by brand
new_by_brand = defaultdict(list)
for s, prod in new_syn_prod.items():
    ns=N(s)
    if ns: new_by_brand[brand(ns)].append((s, ns, prod))

remove=defaultdict(set); evidence=[]
for b, news in new_by_brand.items():
    spells = spell_by_brand.get(b, [])
    for raw, nr in spells:
        if len(nr.split()) <= 1:
            continue                 # bare single-token brand spelling = ambiguous, not steal evidence
        q, qs = c0_best(nr, b)
        if q is None:
            continue                 # unmatched in C0 -> any new match is improvement
        for s, ns, prod in news:
            if prod == q:
                continue             # new syn belongs to the SAME product T already matched
            sc = rt(nr, ns)
            # require the new syn to STRICTLY beat the C0 winner (ties are order-dependent
            # and dominated by bare-token noise) OR be a near-exact (>=0.97) capture.
            if sc >= 0.85 and (sc > qs + 1e-9 or sc >= 0.97):
                remove[prod].add(s)
                evidence.append((raw, q, prod, s, round(sc,2), round(qs,2)))

nrm=sum(len(v) for v in remove.values())
print(f"collapse-causing new synonyms: {nrm}")
seen=set()
for raw,q,p,s,sc,qs in sorted(evidence):
    if s in seen: continue
    seen.add(s)
    print(f"  {s!r} (->{p!r}) steals {raw!r} from {q!r}  [{sc} vs {qs}]")
json.dump({c:sorted(v) for c,v in remove.items()}, open("scripts/_hijack_final_remove.json","w",encoding="utf-8"), ensure_ascii=False, indent=2)

if APPLY and remove:
    n=0
    for p in CUR:
        c=p.get("canonical_name")
        if c in remove:
            before=len(p.get("synonyms",[]))
            p["synonyms"]=[s for s in p["synonyms"] if s not in remove[c]]
            n+=before-len(p["synonyms"])
    payload=json.dumps(CUR,indent=2,ensure_ascii=False)+"\n"
    for m in MIRRORS: open(m,"w",encoding="utf-8").write(payload)
    print(f"\nremoved {n} -> total {sum(len(p.get('synonyms',[])) for p in CUR)}")
