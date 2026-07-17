import json, sys, re
from pathlib import Path
sys.path.insert(0, ".")
from difflib import SequenceMatcher
import core.product_master as PM
from core.product_master import _normalize_name as N
from extractors import stock_pdf
MAN = json.load(open("tests/regression_manifest.json", encoding="utf-8"))
REPORTS = Path(MAN.get("reports_root", "D:/Devs/Reports/Data"))
merged = set(json.load(open("scripts/_hb_merged.json", encoding="utf-8"))["spellings"].keys())
mergednorm = {N(s) for s in merged}
CAT = PM.load_master_catalog()
def m(raw):
    nr=N(raw); 
    if not nr: return (None,None,0,None)
    best=(None,None,0,None)
    for pr in CAT:
        for kind,c in [("canon",pr.get("canonical_name",""))]+[("syn",s) for s in pr.get("synonyms",[])]:
            nc=N(c)
            if not nc: continue
            if nr==nc: return (pr,c,1.0,kind)
            sc=0.90 if ((nc in nr or nr in nc) and len(nc)>=4) else SequenceMatcher(None,nr,nc).ratio()
            if sc>best[2]: best=(pr,c,sc,kind)
    return best if best[2]>=0.85 else (None,None,best[2],None)
allf={p.name:p for p in REPORTS.rglob("*") if p.is_file()}
for fn in ["TIRUPATI MEDICOSE - DERMA.Pdf","VENUS PHARMA (A.BAD) - COSMO.PDF"]:
    res=stock_pdf.extract(allf[fn].read_bytes(),{"filename":fn})
    byc={}
    for r in res.get("rows") or []:
        raw=r.get("raw_product_name") or r.get("product_name"); canon=r.get("product_name")
        if raw: byc.setdefault(canon,[]).append(raw)
    print(f"\n==== {fn} ====")
    for canon,raws in byc.items():
        u=sorted(set(raws))
        if len(u)<2: continue
        info=[(raw,)+m(raw)[1:] for raw in u]
        if any((c in merged or N(c) in mergednorm) and k=="syn" for _,c,_,k in info):
            print(f"  COLLAPSE -> {canon!r}")
            for raw,c,sc,k in info:
                isnew=(c in merged or N(c) in mergednorm)
                print(f"     {raw!r:42} via {'NEW' if (isnew and k=='syn') else k} {c!r} ({round(sc,2)})")
