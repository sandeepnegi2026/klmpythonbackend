"""Fast, principled removal of generic-hijacker NEW synonyms.

Runtime hijack mechanism: a new synonym S filed under host P whose normalized form
is a substring of (or equal to) a DIFFERENT product's canonical name will, via the
matcher's containment bonus (0.90), steal that other product's rows -> collapse.
So: remove any new synonym S (len>=4 norm) whose norm is contained in / equals the
canonical-name norm of a product other than its host. Keeps host-specific synonyms
(e.g. 'LULIZOL XL 50GM') and improvements; drops bare-brand / cross-variant generics
(e.g. 'LULIZOL', 'CETALORE-10', 'NIOSOL -F CREAM' under the wrong sibling).
Pure substring ops -> instant. --apply writes both mirrors.
"""
import json, sys
sys.path.insert(0, ".")
from core.product_master import _normalize_name as N

APPLY = "--apply" in sys.argv
MIRRORS = ["data/product_master.json", "../Backends/data/product_master.json"]
CUR = json.load(open(MIRRORS[0], encoding="utf-8"))
safe_added = json.load(open("scripts/_safe_added.json", encoding="utf-8"))

canon_norm = {p.get("canonical_name"): N(p.get("canonical_name","")) for p in CUR}

remove = {}   # host canonical -> [synonyms]
for host, syns in safe_added.items():
    hostn = canon_norm.get(host, "")
    for s in syns:
        ns = N(s)
        if len(ns) < 4:
            remove.setdefault(host, []).append((s, "too-short generic")); continue
        for other, on in canon_norm.items():
            if other == host or not on:
                continue
            if ns == on or (ns in on and len(ns) >= 4):
                remove.setdefault(host, []).append((s, f"norm in sibling {other!r}")); break

flat = [(h, s, why) for h, lst in remove.items() for (s, why) in lst]
print(f"generic-hijacker NEW synonyms to remove: {len(flat)}")
for h, s, why in flat[:60]:
    print(f"  {s!r}  (host {h!r})  -- {why}")

rm_set = {(h, s) for h, lst in remove.items() for (s, _) in lst}
if APPLY:
    # only remove if currently present (some already gone via earlier surgical fixes)
    n = 0
    for p in CUR:
        h = p.get("canonical_name")
        before = len(p.get("synonyms", []))
        p["synonyms"] = [s for s in p.get("synonyms", []) if (h, s) not in rm_set]
        n += before - len(p["synonyms"])
    payload = json.dumps(CUR, indent=2, ensure_ascii=False) + "\n"
    for m in MIRRORS: open(m, "w", encoding="utf-8").write(payload)
    print(f"\nremoved {n} synonyms -> both mirrors, total {sum(len(p.get('synonyms',[])) for p in CUR)}")
