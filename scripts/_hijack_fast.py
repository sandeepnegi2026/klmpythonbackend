"""FAST static hijack audit. CUR = C0 + new synonyms, so a spelling's match only
changes if some NEW synonym beats its C0 winner. We only fully-evaluate spellings a
new synonym can actually reach (exact normalized equality or containment, which is
how the runtime matcher's 0.90 bonus fires), then compare C0 winner vs new-synonym
winner. Seconds, not minutes, and comprehensive over every known real spelling."""
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
# new synonym -> its product canonical
new_syn_prod = {}
for canonical, syns in safe_added.items():
    for s in syns: new_syn_prod[s] = canonical

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

known = set()
for fn in ["_synonym_spellings_cache_26june.json","_synonym_spellings_cache.json",
           "_synonym_spellings_cache_fullcorpus.json","_hb_merged.json"]:
    known |= set(json.load(open("scripts/"+fn, encoding="utf-8"))["spellings"].keys())
# keep only PLAUSIBLE product spellings (drops footer blobs + bare numbers/fragments)
known = {raw for raw in known if B._is_plausible_product(raw, N(raw))}
nspell = {raw: N(raw) for raw in known}
print(f"{len(known)} plausible spellings, {len(new_syn_prod)} new synonyms")

# new synonyms normalized, indexed by product
new_norm = [(s, N(s), prod) for s, prod in new_syn_prod.items() if N(s)]

def rt_one(nr, nc):
    if not nc: return 0.0
    if nr==nc: return 1.0
    if (nc in nr or nr in nc) and len(nc)>=4: return 0.90
    return SequenceMatcher(None,nr,nc).ratio()

def reach_fast(nr, ns):
    """Exact/containment reach only (no fuzzy) — the 0.90 runtime-bonus mechanism."""
    if not ns: return 0.0
    if nr==ns: return 1.0
    if (ns in nr or nr in ns) and len(ns)>=4: return 0.90
    return 0.0

def c0_match(raw):
    PM._PRODUCT_MASTER = C0
    return PM.normalize_product(raw)

remove = {}; regress=[]; improve=0
for raw, nr in nspell.items():
    # best NEW synonym reaching this spelling by exact/containment (fast)
    best = (0.0, None, None)
    for s, ns, prod in new_norm:
        sc = reach_fast(nr, ns)
        if sc > best[0]:
            best = (sc, s, prod)
            if sc == 1.0: break
    if best[0] < 0.85:
        continue                      # no new synonym reaches this spelling -> match unchanged
    # this spelling is reachable by a new synonym; compare C0 winner vs the new winner
    q = c0_match(raw); qc = q.get("canonical_name") if q else None
    pc = best[2]                       # product the new synonym would pull it to
    # Does the new synonym actually win at runtime? It wins if its score >= C0 best score.
    # Approximate C0 best score via containment/exact against the C0 winner's candidates.
    if qc is None:
        improve += 1; continue         # was unmatched, now matched by a new syn = improvement
    if pc == qc:
        continue                       # new syn maps to the SAME product = harmless reinforcement
    # compute C0 winner's score for this raw to see if the new syn outranks it
    PM._PRODUCT_MASTER = C0
    qprod = next(p for p in C0 if p.get("canonical_name")==qc)
    q_score = max((rt_one(nr, N(c)) for c in [qprod.get("canonical_name","")]+qprod.get("synonyms",[])), default=0)
    if best[0] >= q_score:              # new syn ties/beats C0 winner -> hijack
        remove.setdefault(pc, set()).add(best[1])
        regress.append((raw, qc, pc, best[1], round(best[0],2), round(q_score,2)))

print(f"REGRESSIONS: {len(regress)}   IMPROVEMENTS: {improve}   culprit synonyms: {sum(len(v) for v in remove.values())}")
for raw,q,p,syn,bs,qs in sorted(regress)[:60]:
    print(f"  {raw!r}: {q!r} -> {p!r}  via {syn!r} ({bs} vs base {qs})")
json.dump({c:sorted(s) for c,s in remove.items()}, open("scripts/_hijack_remove.json","w",encoding="utf-8"), ensure_ascii=False, indent=2)

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
    print(f"\nremoved {n} culprits -> both mirrors, total {sum(len(p.get('synonyms',[])) for p in CUR)}")
