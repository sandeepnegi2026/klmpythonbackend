"""Pinpoint exact culprit new synonyms for a set of files (route auto-detected from
baseline). Diffs enrichment under clean C0 vs current; for each product that
collapsed/swapped away, finds the new synonym that captured its raw. --apply removes."""
import json, copy, sys
from pathlib import Path
from difflib import SequenceMatcher
sys.path.insert(0, ".")
import build_product_synonyms as B
import core.product_master as PM
from core.product_master import _normalize_name as N
from extractors import party_pdf, party_xlsx, stock_pdf, stock_xlsx
ROUTES={"party_pdf":party_pdf.extract,"party_xlsx":party_xlsx.extract,"stock_pdf":stock_pdf.extract,"stock_xlsx":stock_xlsx.extract}

APPLY = "--apply" in sys.argv
FILES = [a for a in sys.argv[1:] if a != "--apply"]
MIRRORS=["data/product_master.json","../Backends/data/product_master.json"]
CUR=json.load(open(MIRRORS[0],encoding="utf-8"))
safe_added=json.load(open("scripts/_safe_added.json",encoding="utf-8"))
new_syns={s for v in safe_added.values() for s in v}

base_by_canon={p.get("canonical_name"):p for p in json.load(open(
    r"C:\Users\Sandeep\Downloads\KLM\stock-backends\data\product_master.json",encoding="utf-8"))}
C0=copy.deepcopy(CUR)
for p in C0:
    b=base_by_canon.get(p.get("canonical_name")); p["synonyms"]=list(b.get("synonyms",[])) if b else []
def _apply(cat,sp):
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
_apply(C0,json.load(open("scripts/_synonym_spellings_cache_26june.json",encoding="utf-8"))["spellings"])
assert sum(len(p.get("synonyms",[])) for p in C0)==5462

BL=Path("tests/baselines")
REPORTS=Path(json.load(open("tests/regression_manifest.json",encoding="utf-8")).get("reports_root","D:/Devs/Reports/Data"))
allf={p.name:p for p in REPORTS.rglob("*") if p.is_file()}
def rt(nr,c):
    nc=N(c)
    if not nc: return 0
    if nr==nc: return 1.0
    if (nc in nr or nr in nc) and len(nc)>=4: return .9
    return SequenceMatcher(None,nr,nc).ratio()
def esets(cat,route,p):
    PM._PRODUCT_MASTER=cat
    res=ROUTES[route](p.read_bytes(),{"filename":p.name})
    byc={}
    for r in res.get("rows") or []:
        raw=r.get("raw_product_name") or r.get("product_name"); c=r.get("product_name")
        if raw is not None: byc.setdefault(c,set()).add(raw)
    return byc
remove={}
for fn in FILES:
    bls=list(BL.glob(f"*/{fn}.json"))
    if not bls or fn not in allf: print(f"?? {fn}"); continue
    route=json.load(open(bls[0],encoding="utf-8"))["route"]; p=allf[fn]
    a=esets(C0,route,p); b=esets(CUR,route,p)
    van=set(a)-set(b); app=set(b)-set(a)
    print(f"\n== {fn} [{route}] base={len(a)} cur={len(b)} ==")
    print(f"   vanished={sorted(van)}")
    print(f"   appeared={sorted(app)}")
    PM._PRODUCT_MASTER=CUR
    for v in van:
        for raw in sorted(a[v]):
            mm=PM.normalize_product(raw); now=mm.get("canonical_name") if mm else None
            if now!=v and now is not None:
                P=next(pp for pp in CUR if pp.get("canonical_name")==now)
                cand=sorted(((rt(N(raw),s),s) for s in P.get("synonyms",[]) if s in new_syns),reverse=True)
                if cand and cand[0][0]>=0.85:
                    remove.setdefault(now,set()).add(cand[0][1])
                    print(f"   FIX: raw {raw!r} {v!r}->{now!r}  culprit {cand[0][1]!r}")
print("\n=== culprits ===")
for c,ss in remove.items():
    for s in ss: print(f"   {c!r}: {s!r}")
if APPLY and remove:
    n=0
    for p in CUR:
        c=p.get("canonical_name")
        if c in remove:
            before=len(p["synonyms"]); p["synonyms"]=[s for s in p["synonyms"] if s not in remove[c]]; n+=before-len(p["synonyms"])
    payload=json.dumps(CUR,indent=2,ensure_ascii=False)+"\n"
    for m in MIRRORS: open(m,"w",encoding="utf-8").write(payload)
    print(f"\nremoved {n} -> total {sum(len(p.get('synonyms',[])) for p in CUR)}")
