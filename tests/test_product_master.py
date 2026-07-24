#!/usr/bin/env python3
"""
Unit tests for the KLM D3 family fixes in core.product_master:
  FIX-A  count-pack sibling snap (1*4 Cap vs 1*8 Cap) via _norm_count / _count_key /
         _count_pack_correct, wired into enrich_rows_with_master when no volumetric size.
  FIX-B  ambiguous-stub blocklist (_AMBIGUOUS_STUBS) — bare "KLM D3" / "KLM-D3+" resolve
         to None instead of a catalog-order-arbitrary sibling.
  FIX-C  catalog aliases (validated against the live catalog).

Run standalone (no pytest needed):
    python tests/test_product_master.py        # expect: all passed
"""
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import core.product_master as pm


def _canon(name, pack=""):
    """Enrich a single reconstructed row and return its canonical name (or None)."""
    row = {"product_name": name, "pack": pack}
    out = pm.enrich_rows_with_master([row])[0]
    return out.get("canonical_name")


def _code(name, pack=""):
    row = {"product_name": name, "pack": pack}
    out = pm.enrich_rows_with_master([row])[0]
    return out.get("product_code")


def run():
    passed = 0
    fails = []

    def check(cond, msg):
        nonlocal passed
        if cond:
            passed += 1
        else:
            fails.append(msg)

    pm.load_master_catalog()
    pm.normalize_product("warmup")  # force index build

    # ---- 1. _norm_count truth table -----------------------------------------
    DANGER = ["KLM D3 60K CAP", "KLM-D3 60000K CAP", "KL CLAV 625 TAB", "1000 TAB",
              "HISTABIL 40MG TAB", "800 IU DROPS", "800IU", "4X5ML", "2X100ML",
              "1*100ML", "30ML", "10 x 1 g", "60GM+60GM", "5 ml x 10 Bottles",
              "EXP 10/26", "B.NO 4S21", "10 STP", "1 Box"]
    for d in DANGER:
        check(pm._norm_count(d) == "", f"_norm_count danger {d!r} -> {pm._norm_count(d)!r} (want '')")
    TRUE = {"1*4CAP": "c4", "1*8": "c8", "1X8": "c8", "4'S": "c4", "4S": "c4",
            "10 S": "c10", "10 TAB": "c10", "8PCS": "c8", "1*30": "c30", "20 Tab": "c20",
            "KLM D3 60K CAPS 1*8'S": "c8", "HERPIVAL 1000 3'S": "c3",
            "RESOTEN-10 CAP": "c10", 'KLM-D3 60K CAP 4"S': "c4"}
    for t, exp in TRUE.items():
        check(pm._norm_count(t) == exp, f"_norm_count {t!r} -> {pm._norm_count(t)!r} (want {exp})")

    # ---- 2. _count_key groups counts, splits strengths ----------------------
    check(pm._count_key("Klm-D3 60K Capsules (1*4Cap)") ==
          pm._count_key("Klm-D3 60K Capsules (1*8 Cap)"),
          "_count_key: 60K 1*4 and 1*8 must share a key")
    check(pm._count_key("Resoten 10") != pm._count_key("Resoten 20"),
          "_count_key: Resoten 10 / 20 must stay distinct (strength kept)")

    # ---- 3. Catalog-as-oracle: count-index multi-member groups are exactly the 3 ----
    multi = {k for k, v in pm._COUNT_INDEX.items() if len(v) > 1}
    check(multi == {"klm d3 60k", "extend hair", "klm c 1000"},
          f"count-index multi-groups drifted: {sorted(multi)}")

    # ---- 4. FIX-A end-to-end: 60K count snap --------------------------------
    check(_code("KLM-D3 60K CAP", "1*4CAP") == "D360K",
          f"60K + 1*4CAP should snap to D360K, got {_code('KLM-D3 60K CAP', '1*4CAP')}")
    check(_code("KLM-D3 60K CAP", "1*8") == "D360K2",
          f"60K + 1*8 should be D360K2, got {_code('KLM-D3 60K CAP', '1*8')}")
    # bare 60K with 1*4 pack still snaps to D360K (via new exact alias base -> count snap)
    check(_code("KLM D3 60K", "1*4") == "D360K",
          f"bare 60K + 1*4 should snap to D360K, got {_code('KLM D3 60K', '1*4')}")
    check(_code("KLM D3 60K", "1*8") == "D360K2",
          f"bare 60K + 1*8 should be D360K2, got {_code('KLM D3 60K', '1*8')}")
    # _seen non-contamination: same raw name, different pack counts -> different SKUs
    rows = [{"product_name": "KLM-D3 60K CAP", "pack": "1*4CAP"},
            {"product_name": "KLM-D3 60K CAP", "pack": "1*8"}]
    out = pm.enrich_rows_with_master(rows)
    check(out[0].get("product_code") == "D360K" and out[1].get("product_code") == "D360K2",
          f"_seen contamination: {out[0].get('product_code')}, {out[1].get('product_code')}")

    # ---- 5. Volumetric path untouched (no count interference) ---------------
    check(_canon("KLM D3 NANO DROPS", "30ML") == "Klm D3 Nano Drops 30Ml",
          f"nano drops 30ml must stay ml-snapped, got {_canon('KLM D3 NANO DROPS', '30ML')}")
    check(_canon("KLM D3 NANO DROPS", "15ML") == "Klm D3 Nano Drops",
          f"nano drops 15ml, got {_canon('KLM D3 NANO DROPS', '15ML')}")

    # ---- 6. FIX-B ambiguous-stub blocklist ----------------------------------
    check(pm.normalize_product("KLM D3") is None, "bare 'KLM D3' must be None (FIX-B)")
    check(pm.normalize_product("KLM-D3+") is None, "'KLM-D3+' must be None (FIX-B)")
    check(pm.normalize_product("KLM-D3 +") is None, "'KLM-D3 +' must be None (FIX-B)")
    # a fuller name is NOT blocked
    check(_canon("KLM D3 NANO DROPS 15ML") == "Klm D3 Nano Drops",
          "FIX-B must not shadow longer names")

    # ---- 7. FIX-C aliases resolve --------------------------------------------
    check(_code("KLM D3 SHOTS") == "KLM 14", f"'KLM D3 SHOTS' -> {_code('KLM D3 SHOTS')}")
    check(_code("KLM D3 SHOT") == "KLM 14", f"'KLM D3 SHOT' -> {_code('KLM D3 SHOT')}")
    check(_code("KLM D3 800IU NANO DROPS") == "KLM 10",
          f"'KLM D3 800IU NANO DROPS' -> {_code('KLM D3 800IU NANO DROPS')}")
    check(_code("KLM-D3 60K SOFTGEL", "1*4") == "D360K",
          f"softgel + 1*4 -> {_code('KLM-D3 60K SOFTGEL', '1*4')}")

    # ---- 8. Regression pins: unrelated brands unaffected --------------------
    # (bare RESOTEN behavior held; a genuine ml row still enriches)
    check(_canon("ZYDIP LOTION", "50ML") is not None,
          "ZYDIP LOTION 50ML must still enrich (size path intact)")

    print(f"{passed} passed, {len(fails)} failed")
    for f in fails:
        print("  FAIL:", f)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(run())
