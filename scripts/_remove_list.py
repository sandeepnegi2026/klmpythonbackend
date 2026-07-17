"""Remove an explicit list of synonym strings from BOTH product_master.json mirrors.
Usage: _remove_list.py <list.json> [<list2.json> ...]   (lists = JSON arrays of strings)
"""
import json, sys
MIRRORS = ["../data/product_master.json", "../../Backends/data/product_master.json"]
remove = set()
for fn in sys.argv[1:]:
    remove |= set(json.load(open(fn, encoding="utf-8")))
print(f"removal set: {len(remove)} synonym strings")
cat = json.load(open(MIRRORS[0], encoding="utf-8"))
removed = 0
for p in cat:
    syn = p.get("synonyms", [])
    kept = [s for s in syn if s not in remove]
    removed += len(syn) - len(kept)
    p["synonyms"] = kept
payload = json.dumps(cat, indent=2, ensure_ascii=False) + "\n"
for m in MIRRORS:
    open(m, "w", encoding="utf-8").write(payload)
tot = sum(len(p.get("synonyms", [])) for p in cat)
print(f"removed {removed} synonyms -> {tot} total, written to both mirrors")
