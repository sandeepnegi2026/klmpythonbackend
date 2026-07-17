"""Pinpoint the exact products that collapsed vs the clean C0 baseline for the two
residual-failing files, and the synonym responsible. Rebuilds C0 (5462) in memory
(June25 + 26june cache), runs enrichment under both catalogs, diffs the canonical
sets per file."""
import json, copy, sys
from pathlib import Path
sys.path.insert(0, ".")
import build_product_synonyms as B
import core.product_master as PM
from core.product_master import _normalize_name as N
from extractors import stock_pdf

JUNE25 = r"C:\Users\Sandeep\Downloads\KLM\stock-backends\data\product_master.json"
CUR = json.load(open("data/product_master.json", encoding="utf-8"))   # 5910

# rebuild clean C0 in memory
base_by_canon = {p.get("canonical_name"): p for p in json.load(open(JUNE25, encoding="utf-8"))}
C0 = copy.deepcopy(CUR)
for p in C0:
    b = base_by_canon.get(p.get("canonical_name"))
    p["synonyms"] = list(b.get("synonyms", [])) if b else []
def apply_cache(cat, sp):
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
apply_cache(C0, json.load(open("scripts/_synonym_spellings_cache_26june.json",encoding="utf-8"))["spellings"])
assert sum(len(p.get("synonyms",[])) for p in C0)==5462

MAN = json.load(open("tests/regression_manifest.json", encoding="utf-8"))
REPORTS = Path(MAN.get("reports_root", "D:/Devs/Reports/Data"))
allf = {p.name: p for p in REPORTS.rglob("*") if p.is_file()}

def products_under(catalog, fn):
    PM._PRODUCT_MASTER = catalog
    res = stock_pdf.extract(allf[fn].read_bytes(), {"filename": fn})
    rows = res.get("rows") or []
    # map canonical -> set of raws
    byc = {}
    for r in rows:
        raw = r.get("raw_product_name") or r.get("product_name")
        canon = r.get("product_name")
        byc.setdefault(canon, set()).add(raw)
    return byc

for fn in ["MANISH MEDICAL AGENCIES - DERMA.PDF"]:
    a = products_under(C0, fn)      # baseline
    b = products_under(CUR, fn)     # current
    vanished = set(a) - set(b)      # in baseline, gone now => collapsed away
    appeared = set(b) - set(a)
    print(f"\n==== {fn}  baseline={len(a)} current={len(b)} ====")
    print(f"  VANISHED (collapsed): {sorted(vanished)}")
    print(f"  APPEARED            : {sorted(appeared)}")
    # for each vanished product, where did its raws go now, and via which synonym
    PM._PRODUCT_MASTER = CUR
    for v in vanished:
        for raw in sorted(a[v]):
            m = PM.normalize_product(raw)
            now = m.get("canonical_name") if m else None
            if now != v:
                # find the winning candidate string
                print(f"    raw {raw!r}: baseline->{v!r}  now->{now!r}")
