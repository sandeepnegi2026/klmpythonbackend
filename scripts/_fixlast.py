"""Find & (optionally) remove the exact new synonyms that capture 3 specific raws
onto the wrong product, restoring TIRUPATI/VENUS to baseline."""
import json, sys
from difflib import SequenceMatcher
sys.path.insert(0, ".")
from core.product_master import _normalize_name as N

APPLY = "--apply" in sys.argv
MIRRORS = ["data/product_master.json", "../Backends/data/product_master.json"]
CAT = json.load(open(MIRRORS[0], encoding="utf-8"))
safe_added = json.load(open("scripts/_safe_added.json", encoding="utf-8"))
new_syns = {s for v in safe_added.values() for s in v}

# (raw, wrong canonical it currently grabs)
PROBLEMS = [
    ("CETALORE 10", "Cetalore-M Tablet"),
    ("CETALORE-10", "Cetalore-M Tablet"),
    ("NEVLON XL",   "Nevlon Lotion 100Ml"),
]
def rt(nr, cand):
    nc = N(cand)
    if not nc: return 0.0
    if nr == nc: return 1.0
    if (nc in nr or nr in nc) and len(nc) >= 4: return 0.90
    return SequenceMatcher(None, nr, nc).ratio()

remove = {}  # canonical -> set(synonyms)
for raw, wrong in PROBLEMS:
    nr = N(raw)
    P = next(p for p in CAT if p.get("canonical_name") == wrong)
    # the synonym(s) under P that score highest for this raw AND are new additions
    scored = sorted(((rt(nr, s), s) for s in P.get("synonyms", [])), reverse=True)
    print(f"\nraw {raw!r} under {wrong!r}: top candidates")
    for sc, s in scored[:5]:
        new = "NEW" if s in new_syns else "old"
        print(f"   {sc:.2f} [{new}] {s!r}")
    # remove the top-scoring NEW synonyms that meet/exceed the canonical-containment 0.9
    canon_sc = rt(nr, wrong)
    for sc, s in scored:
        if s in new_syns and sc >= max(0.90, canon_sc):
            remove.setdefault(wrong, set()).add(s)

print("\n=> TO REMOVE:")
for c, ss in remove.items():
    for s in ss: print(f"   {c!r} : {s!r}")

if APPLY:
    n = 0
    for p in CAT:
        c = p.get("canonical_name")
        if c in remove:
            before = len(p["synonyms"])
            p["synonyms"] = [s for s in p["synonyms"] if s not in remove[c]]
            n += before - len(p["synonyms"])
    payload = json.dumps(CAT, indent=2, ensure_ascii=False) + "\n"
    for m in MIRRORS: open(m, "w", encoding="utf-8").write(payload)
    print(f"\nremoved {n} synonyms -> both mirrors, total {sum(len(p.get('synonyms',[])) for p in CAT)}")
