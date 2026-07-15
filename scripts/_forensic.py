"""Forensic: for given stock files, simulate the RUNTIME matcher
(core.product_master.normalize_product) instrumented to reveal the winning
candidate, and report product collapses (>1 distinct raw spelling -> same
canonical) plus, for each, the culprit synonym and whether it is a NEW (this-run,
merged-cache) string. This pinpoints exactly which synonyms to drop to undo the
wrong collapses while keeping the genuinely-new safe synonyms.
"""
import json, sys, re
from pathlib import Path
sys.path.insert(0, ".")
from difflib import SequenceMatcher
import core.product_master as PM
from core.product_master import _normalize_name as N
from extractors import stock_pdf

ROOT = Path(".").resolve()
MAN = json.load(open("tests/regression_manifest.json", encoding="utf-8"))
REPORTS = Path(MAN.get("reports_root", "D:/Devs/Reports/Data"))
merged = set(json.load(open("scripts/_hb_merged.json", encoding="utf-8"))["spellings"].keys())
mergednorm = {N(s) for s in merged}

CAT = PM.load_master_catalog()

def match_instrumented(raw, min_score=0.85):
    """Mirror normalize_product but return (product, candidate, score, kind)."""
    norm_raw = N(raw)
    if not norm_raw: return (None, None, 0.0, None)
    best = (None, None, 0.0, None)
    for product in CAT:
        cands = [("canon", product.get("canonical_name",""))] + \
                [("syn", s) for s in product.get("synonyms", [])]
        for kind, cand in cands:
            if not cand: continue
            nc = N(cand)
            if not nc: continue
            if norm_raw == nc:
                return (product, cand, 1.0, kind)
            if (nc in norm_raw or norm_raw in nc) and len(nc) >= 4:
                sc = 0.90
            else:
                sc = SequenceMatcher(None, norm_raw, nc).ratio()
            if sc > best[2]:
                best = (product, cand, sc, kind)
    if best[2] >= min_score:
        return best
    return (None, None, best[2], None)

FAILING = [
 "TIRUPATI MEDICOSE - DERMA.Pdf","VENUS PHARMA (A.BAD) - COSMO.PDF",
 "AHUJA MEDICAL AGENCY (KATNI) - PEDIA.PDF","ANIL PHARMA DISTRIBUTORS - DERMACOR.pdf",
 "DAHOD PHARMAKON - PEDIA.pdf","JINDAL MEDICAL AGENCIES - DERMA.pdf",
 "KRISHNA CARE (MAA BANJARI) - PEDIA.PDF","N.K.MEDICAL (ZEN MEDICOSE) - PEDIA.PDF",
 "OMKAR ENTERPRIES - PEDIA.pdf","TIRUPATI MEDICOSE - DERMA.Pdf",
 "VENUS PHARMA (A.BAD) - COSMO.PDF","VISNAGAR MEDICAL STORES - COSMO.pdf",
 "MANISH MEDICAL AGENCIES - DERMA.PDF","SOURABH MEDICOSE - DERMACOR.pdf",
]

# locate files anywhere under reports root
allfiles = {p.name: p for p in REPORTS.rglob("*") if p.is_file()}
culprits = {}   # synonym -> count of collapses it causes
for fn in FAILING:
    p = allfiles.get(fn)
    if not p:
        print(f"?? not found: {fn}"); continue
    res = stock_pdf.extract(p.read_bytes(), {"filename": fn})
    rows = res.get("rows") or []
    bycanon = {}
    for r in rows:
        raw = r.get("raw_product_name") or r.get("product_name")
        canon = r.get("product_name")
        if not raw: continue
        bycanon.setdefault(canon, []).append(raw)
    print(f"\n===== {fn} =====")
    for canon, raws in bycanon.items():
        uniq = sorted(set(raws))
        if len(uniq) < 2: continue          # only multi-raw canonicals (possible collapse)
        # re-match each raw to see winning candidate
        info = []
        for raw in uniq:
            prod, cand, sc, kind = match_instrumented(raw)
            isnew = (cand in merged) or (N(cand) in mergednorm)
            info.append((raw, cand, round(sc,2), kind, isnew))
        # flag if any raw wins via a NEW synonym (likely intruder)
        if any(i[4] and i[3]=="syn" for i in info):
            print(f"  COLLAPSE -> {canon!r}")
            for raw, cand, sc, kind, isnew in info:
                tag = "NEW-SYN" if (isnew and kind=='syn') else kind
                print(f"      raw={raw!r:45} via {tag} {cand!r} ({sc})")
                if isnew and kind=="syn":
                    culprits[cand] = culprits.get(cand,0)+1

print("\n\n===== CULPRIT NEW SYNONYMS (cause collapses) =====")
for s,c in sorted(culprits.items(), key=lambda x:-x[1]):
    print(f"  x{c}  {s!r}")
json.dump(list(culprits), open("scripts/_collapse_culprits.json","w",encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"\n{len(culprits)} distinct culprit synonyms -> scripts/_collapse_culprits.json")
