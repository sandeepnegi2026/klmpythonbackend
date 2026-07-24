#!/usr/bin/env python3
"""
Catalog-seeded regression test for core.pack_match.extract_pack_from_product.

The product_master catalog is the ORACLE: every product has a real pack, and every
canonical_name / synonym is a real product string. The invariant we lock in:

  * A peeled pack is ALWAYS number-led (a measure / count) — never a bare dosage-form
    word (LOTION, CREAM, SOAP, DROPS, ...). So a product name is never truncated to a
    bare brand ("IMXIA 5 LOTION" must not become "IMXIA").

Run standalone (no pytest needed):
    python tests/test_pack_match.py        # expect: all passed
"""
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import core.product_master as pm
from core.pack_match import extract_pack_from_product as ex

# Dosage-form / name words that must NEVER be the head of a peeled pack.
NAME_FORMS = {
    "LOTION", "CREAM", "GEL", "SOAP", "OINTMENT", "OINT", "SYRUP", "SYP",
    "SUSPENSION", "SUSP", "DROPS", "DROP", "BAR", "POWDER", "SERUM", "EMULGEL",
    "SHAMPOO", "FACEWASH", "TABLET", "TABLETS", "CAPSULE", "CAPSULES", "SOLUTION",
    "SPRAY", "CRE", "SOA", "LOT", "PES",
}


def _is_bad_pack(pack):
    """A peeled pack is bad if it has no digit, or ends in a dosage-form word."""
    if not pack:
        return False
    if not re.search(r"\d", pack):
        return True
    words = re.findall(r"[A-Za-z]+", pack)
    return bool(words) and words[-1].upper() in NAME_FORMS


def run():
    passed = failed = 0
    fails = []

    # ---- 1. No product string in the whole catalog loses a form word to "pack" ----
    cat = pm.load_master_catalog()
    strings = []
    for p in cat:
        strings.append(str(p.get("canonical_name", "")))
        strings.extend(str(s) for s in p.get("synonyms", []))
    strings = [s for s in strings if s and s.strip()]
    bad = [(s, ex(s)) for s in strings if _is_bad_pack(ex(s)[1])]
    if bad:
        failed += 1
        fails.append(f"[catalog no-form-strip] {len(bad)}/{len(strings)} strings peeled a form word, e.g. "
                     + "; ".join(f"{s!r}->{r}" for s, r in bad[:5]))
    else:
        passed += 1

    # ---- 2. Reported cases: the name is preserved, no false pack ----
    keep_whole = ["IMXIA 5 LOTION", "EKRAN LOTION", "Kenz Soap", "Moxiview Eye Drops",
                  "AZACEA 10 CREAM", "Enzotret Tab", "Something Box", "KOJITIN ULTRA CREAM"]
    for s in keep_whole:
        base, pack = ex(s)
        if (base, pack) == (s, ""):
            passed += 1
        else:
            failed += 1
            fails.append(f"[keep-whole] {s!r} -> base={base!r} pack={pack!r} (expected name unchanged, no pack)")

    # ---- 3. Genuine measure/count packs still peel ----
    peel = {
        "XEROLENE CREAM 50GM": ("XEROLENE CREAM", "50GM"),
        "IMXIA F 5% 60ML": ("IMXIA F 5%", "60ML"),
        "NIOFINE TAB 7TAB": ("NIOFINE TAB", "7TAB"),
        "RESOTEN-NF 2 ml": ("RESOTEN-NF", "2 ml"),
        "BRAND 1*10": ("BRAND", "1*10"),
        "BRAND 10'S": ("BRAND", "10'S"),
        "BRAND 5MG": ("BRAND", "5MG"),
    }
    for s, exp in peel.items():
        got = ex(s)
        if got == exp:
            passed += 1
        else:
            failed += 1
            fails.append(f"[peel] {s!r} -> {got} (expected {exp})")

    # ---- 4. Container-of dialect: size mid-string, FORM word kept in the name ----
    # The size behind "TUBE OF"/"BOX OF"/"BOTTLE OF" is pulled as pack; the container
    # filler is dropped; the trailing form word STAYS so downstream matching can pick
    # the right form/size sibling. Trailing size (no container) is unaffected (§3).
    container = {
        "EPISERT TUBE OF 30GM CREAM": ("EPISERT CREAM", "30GM"),
        "LULIZOL TUBE OF 20GM CREAM": ("LULIZOL CREAM", "20GM"),
        "LULIZOL BOTTLE OF 20ML LOTION": ("LULIZOL LOTION", "20ML"),
        "ZYDIP C BOTTLE OF 30ML LOTION": ("ZYDIP C LOTION", "30ML"),
        "KENZ BOX OF 75GM SOAP": ("KENZ SOAP", "75GM"),
        "NIOSALIC 6 TUBE OF 20GM OINTMENT": ("NIOSALIC 6 OINTMENT", "20GM"),
        "EKRAN SPF 30 PLUS TUBE OF 50GM AQUA GEL": ("EKRAN SPF 30 PLUS AQUA GEL", "50GM"),
        "GA 6 TUBE OF 30GM CREAM": ("GA 6 CREAM", "30GM"),
        # dangling container with no size -> strip the filler, keep the name whole
        "KLMKLIN AHA FACE WASH TUBE OF": ("KLMKLIN AHA FACE WASH", ""),
    }
    for s, exp in container.items():
        got = ex(s)
        if got == exp:
            passed += 1
        else:
            failed += 1
            fails.append(f"[container] {s!r} -> {got} (expected {exp})")

    print(f"pack_match: {passed} passed, {failed} failed"
          f"  (catalog population: {len(strings)} strings)")
    for f in fails:
        print("  FAIL:", f)
    return failed == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
