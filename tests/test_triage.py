"""
Unit tests for the triage layer (core/triage.py + core/quality.py).

These feed synthetic extraction `result` dicts straight into build_quality and
assert the bucket + reason_code, so they run instantly and need no sample files.
They lock in the "no misleading error" rules: a clean extraction is GREEN, an
unambiguous failure is RED with a specific reason, and everything uncertain is
AMBER (never a silent pass).

Run:  python -m pytest tests/test_triage.py -q     (from the Backends dir)
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import pytest
except ModuleNotFoundError:  # allow standalone run without pytest installed
    class _Mark:
        @staticmethod
        def skipif(cond, reason=""):
            def deco(fn):
                fn.__skip__ = (bool(cond), reason)
                return fn
            return deco

    class _Pytest:
        mark = _Mark()

    pytest = _Pytest()  # type: ignore

from core.product_master import load_master_catalog, normalize_product
from core.quality import build_quality

# Real catalog names so product_master_match_rate doesn't drag a clean fixture
# down to AMBER for the wrong reason.
_CATALOG = load_master_catalog() or []
_GOOD_NAMES = [
    (p.get("canonical_name") or p.get("normalized_name") or "")
    for p in _CATALOG
]
_GOOD_NAMES = [n for n in _GOOD_NAMES if n and normalize_product(n)][:12]
_HAVE_CATALOG = len(_GOOD_NAMES) >= 4


def _name(i):
    return _GOOD_NAMES[i % len(_GOOD_NAMES)] if _HAVE_CATALOG else f"PRODUCT {i}"


def stock_rows(n=20, *, closing_ok=True, vary=True):
    rows = []
    for i in range(n):
        op = 10 + (i if vary else 0)
        pur = 5 + (i % 3 if vary else 0)
        sal = 7 + (i % 4 if vary else 0)
        cl = op + pur - sal if closing_ok else 0
        rows.append({
            "product_name": _name(i), "pack": str(10 + i % 2),
            "opening_stock": str(op), "purchase_stock": str(pur),
            "purchase_free": "0", "purchase_return": "0",
            "sales_qty": str(sal), "sales_value": str(sal * 100),
            "sales_free": "0", "sales_return": "0",
            "closing_stock": str(cl), "closing_stock_value": str(cl * 100),
            "vendor_name": "ACME", "report_start_date": "2026-01-01",
            "report_end_date": "2026-01-31", "division": "PHARMA",
        })
    return rows


def stock_result(**kw):
    return {
        "rows": stock_rows(**kw),
        "headers_detected": {"Item": "product_name", "OpStk": "opening_stock",
                             "S.Qty": "sales_qty", "ClStk": "closing_stock"},
        "raw_text": "stock statement report ... data",
        "warnings": [],
        "sanity": {"pass_rate": 1.0},
    }


def party_rows(n=15):
    rows = []
    for i in range(n):
        qty = 2 + i
        rate = 10 + i
        rows.append({
            "party_name": f"SHOP {i % 5}", "invoice_number": f"INV{i}",
            "invoice_date": "2026-01-0%d" % (1 + i % 9), "product_name": _name(i),
            "qty": str(qty), "rate": str(rate), "taxable_value": str(qty * rate),
            "vendor_name": "ACME", "report_start_date": "a", "report_end_date": "b",
            "division": "PHARMA",
        })
    return rows


def party_result(rows=None):
    return {
        "rows": party_rows() if rows is None else rows,
        "headers_detected": {"Party": "party_name", "Item": "product_name",
                             "Qty": "qty", "Rate": "rate"},
        "raw_text": "party wise sales register",
        "warnings": [],
    }


def bucket(result, report_type):
    q = build_quality(result, report_type)
    return q["triage"]["bucket"], q["triage"]["reason_code"]


def verdict(result, report_type):
    """Full triage verdict incl. the human-facing ``reason`` message."""
    return build_quality(result, report_type)["triage"]


def party_value_mostly_zero_rows(n=15, nonzero=3):
    """Party rows whose value dimension (amount/taxable_value/rate) is zero except the
    first ``nonzero`` rows, whose amounts sum to a known control total (600). qty stays
    populated so ONLY the value dimension trips CORE_FIELD_EMPTY."""
    amounts = [100.0, 200.0, 300.0]
    rows = []
    for i in range(n):
        rows.append({
            "party_name": f"SHOP {i % 5}", "invoice_number": f"INV{i}",
            "invoice_date": "2026-01-0%d" % (1 + i % 9), "product_name": _name(i),
            "qty": str(2 + i), "rate": "0", "taxable_value": "0",
            "amount": str(amounts[i] if i < nonzero else 0.0),
            "vendor_name": "ACME", "report_start_date": "a", "report_end_date": "b",
            "division": "PHARMA",
        })
    return rows


def party_reconciling_unmatched_rows(n=15):
    """Party rows whose values are fully populated and sum to a known control total
    (2550), but whose product names are NOT in the master catalog -> a LOW_MASTER_MATCH
    AMBER (a DIFFERENT sanity type from CORE_FIELD_EMPTY). Proves the reassurance is
    universal across AMBER types, not CORE_FIELD_EMPTY-only."""
    rows = []
    for i in range(n):
        amt = 100 + 10 * i
        rows.append({
            "party_name": f"SHOP {i % 5}", "invoice_number": f"INV{i}",
            "invoice_date": "2026-01-0%d" % (1 + i % 9),
            "product_name": f"ZZZ UNKNOWN ITEM {i}",  # won't match catalog
            "qty": str(2 + i), "rate": str(10 + i),
            "taxable_value": str(amt), "amount": str(amt),
            "vendor_name": "ACME", "report_start_date": "a", "report_end_date": "b",
            "division": "PHARMA",
        })
    return rows


# --------------------------------------------------------------------------- #
# RED — unambiguous failures
# --------------------------------------------------------------------------- #
def test_scanned_pdf_is_red():
    b, code = bucket({"rows": [], "headers_detected": {}, "raw_text": "", "warnings": []}, "stock")
    assert b == "RED" and code == "SCANNED_OR_EMPTY"


def test_text_but_no_rows_is_unknown_layout():
    b, code = bucket({"rows": [], "headers_detected": {}, "raw_text": "lots of text here", "warnings": []}, "party")
    assert b == "RED" and code == "UNKNOWN_LAYOUT"


def test_rollup_no_product_column_is_amber():
    # Party roll-up: product_name empty AND no product column in the source (Item header
    # absent from detected_fields). We can't tell a legit party-total roll-up from a broken
    # one, so it must NOT auto-pass GREEN and must NOT hard-reject a possibly-legit roll-up
    # -> AMBER for a human glance. (Regression guard for the GREEN false-pass the cross-check
    # caught: a product-less roll-up used to land GREEN.)
    rows = party_rows()
    for r in rows:
        r["product_name"] = ""
    res = party_result(rows)
    res["headers_detected"].pop("Item", None)  # no product column detected
    b, code = bucket(res, "party")
    assert b == "AMBER" and code == "PRODUCT_ROLLUP"


def test_missing_product_name_with_column_is_red():
    # A real dropped-product bug: the product column WAS detected (Item header present) but
    # every value is empty -> the parser lost the products -> RED, never treated as a roll-up.
    rows = party_rows()
    for r in rows:
        r["product_name"] = ""
    res = party_result(rows)  # keep the Item header -> product_name IS in detected_fields
    b, code = bucket(res, "party")
    assert b == "RED" and code.startswith("MISSING_REQUIRED_FIELD")


def test_all_core_numeric_zero_is_column_misalignment():
    rows = stock_rows()
    for r in rows:  # wipe every core numeric -> no numeric data at all
        r["opening_stock"] = r["sales_qty"] = r["closing_stock"] = "0"
    res = stock_result()
    res["rows"] = rows
    b, code = bucket(res, "stock")
    assert b == "RED" and code == "COLUMN_MISALIGNMENT"


def test_broken_reconciliation_is_sanity_failed():
    b, code = bucket(stock_result(closing_ok=False), "stock")
    assert b == "RED" and code == "SANITY_FAILED"


# --------------------------------------------------------------------------- #
# AMBER — uncertain, must never silently pass
# --------------------------------------------------------------------------- #
def test_single_core_field_zero_is_amber_not_red():
    # opening_stock all zero is legitimate for a new stockist's first period.
    # Keep reconciliation valid (closing = purchase - sales) so this exercises
    # the single-core-empty path, not the sanity path.
    res = stock_result()
    for i, r in enumerate(res["rows"]):
        pur, sal = 10 + i, 3
        r["opening_stock"] = "0"
        r["purchase_stock"] = str(pur)
        r["sales_qty"] = str(sal)
        r["closing_stock"] = str(pur - sal)
        r["closing_stock_value"] = str((pur - sal) * 100)
    b, code = bucket(res, "stock")
    assert b == "AMBER" and code == "CORE_FIELD_EMPTY", f"got {b}/{code}"


def test_core_field_empty_adds_extraction_correct_when_total_reconciles():
    # Value dimension is zero in almost every row (3/15 non-zero) -> CORE_FIELD_EMPTY,
    # BUT the extracted amounts sum to 600, matching the report's own printed grand
    # total. That corroborates the extraction as faithful: the zeros are the vendor's
    # own data, not a dropped column. Stays AMBER, but the reason must reassure.
    res = party_result(party_value_mostly_zero_rows())
    res["raw_text"] = "party wise sales register\nGrand Total : 600.00\n"
    v = verdict(res, "party")
    assert v["bucket"] == "AMBER" and v["reason_code"] == "CORE_FIELD_EMPTY", v
    assert "Extraction is correct" in v["reason"], v["reason"]
    # Still carries the original warning so the reviewer knows WHY it was flagged.
    assert "verify the column mapping" in v["reason"], v["reason"]


def test_extraction_correct_reassurance_is_universal_across_amber_types():
    # A DIFFERENT AMBER type (LOW_MASTER_MATCH, not CORE_FIELD_EMPTY): values are fully
    # populated and reconcile with the printed grand total (2550), but product names miss
    # the catalog. The numbers are provably faithful, so the reassurance must lead here
    # too -- while the specific "verify product names" warning still follows.
    if not _HAVE_CATALOG:
        return  # can't exercise master-match without a catalog to miss
    res = party_result(party_reconciling_unmatched_rows())
    res["raw_text"] = "party wise sales register\nGrand Total : 2550.00\n"
    v = verdict(res, "party")
    assert v["bucket"] == "AMBER" and v["reason_code"] == "LOW_MASTER_MATCH", v
    assert "Extraction is correct" in v["reason"], v["reason"]
    # reassurance is scoped to the numbers, so the actionable name flag is still present
    assert "master catalog" in v["reason"], v["reason"]


def test_core_field_empty_reassures_when_source_lacks_value_column():
    # A qty-only "net sales" report (party_product_net_sales_pdf style): the source prints
    # NO amount/taxable_value/rate column, so the value dimension is legitimately empty and
    # the extraction is faithful. headers_detected carries ONLY the columns the report
    # actually has -> reassure WITHOUT needing a reconciling printed total.
    rows = party_rows()
    for r in rows:
        r["amount"] = r["taxable_value"] = r["rate"] = "0"
    res = party_result(rows)
    res["headers_detected"] = {"Party Name": "party_name",
                               "Product Name": "product_name", "Sale Qty": "qty"}
    res["raw_text"] = "party / product wise net sales register"  # no reconciling total
    v = verdict(res, "party")
    assert v["bucket"] == "AMBER" and v["reason_code"] == "CORE_FIELD_EMPTY", v
    assert "Extraction is correct" in v["reason"], v["reason"]
    assert "prints no" in v["reason"], v["reason"]


def test_core_field_empty_reassures_when_value_column_blank_but_detected():
    # A value column IS in the layout's headers but is blank in EVERY row (0% non-zero).
    # A wholly-empty column is a blank column faithfully reflected, not scattered/dropped
    # data, so it reassures too -- with wording that says the column is blank in the source
    # (vs "prints no ... column" when it was never a header).
    rows = party_rows()
    for r in rows:
        r["amount"] = r["taxable_value"] = r["rate"] = "0"
    res = party_result(rows)
    res["headers_detected"] = {"Party Name": "party_name", "Product Name": "product_name",
                               "Sale Qty": "qty", "Amount": "amount"}
    res["raw_text"] = "party wise sales register"  # no reconciling total
    v = verdict(res, "party")
    assert v["bucket"] == "AMBER" and v["reason_code"] == "CORE_FIELD_EMPTY", v
    assert "Extraction is correct" in v["reason"], v["reason"]
    assert "blank in the source" in v["reason"], v["reason"]


def test_core_field_empty_reassures_for_stock_blank_closing():
    # The user's stock screenshot: closing_stock is emitted by the (dense) stock parser as
    # a key but is zero/blank in EVERY row, while the rows RECONCILE (everything received
    # was sold: closing 0 = opening + purchase - sales). So it is CORE_FIELD_EMPTY, not
    # SANITY_FAILED. Same uniform rule -> reassure. Locks that stock (not just party) gets
    # the "Extraction is correct" line.
    rows = stock_rows()
    for i, r in enumerate(rows):
        op, pur, sal = 10 + i, 5, 15 + i     # base = op + pur - sal = 0 -> closing 0 balances
        r["opening_stock"] = str(op)
        r["purchase_stock"] = str(pur)
        r["purchase_free"] = r["purchase_return"] = "0"
        r["sales_qty"] = str(sal)
        r["sales_free"] = r["sales_return"] = "0"
        r["closing_stock"] = "0"             # blank in every row
        r["closing_stock_value"] = "0"
    res = stock_result()
    res["rows"] = rows
    # dense stock parser emits closing_stock as a detected key even though it is blank
    res["headers_detected"] = {"Item": "product_name", "OpStk": "opening_stock",
                               "Recd": "purchase_stock", "Issue": "sales_qty",
                               "Closing": "closing_stock"}
    res["raw_text"] = "stock statement opening receipt issue closing"  # no reconciling total
    v = verdict(res, "stock")
    assert v["bucket"] == "AMBER" and v["reason_code"] == "CORE_FIELD_EMPTY", v
    assert "Extraction is correct" in v["reason"], v["reason"]
    assert "closing_stock" in v["reason"], v["reason"]


def test_core_field_empty_no_reassure_when_column_partially_populated():
    # Partial, scattered data (value non-zero in 3/15 rows) with NO reconciling total is
    # the fingerprint of a possible mis-aligned/shifted column -> NOT proven faithful, so
    # keep the plain warning (no "Extraction is correct").
    res = party_result(party_value_mostly_zero_rows())  # amount non-zero in 3 of 15 rows
    res["raw_text"] = "party wise sales register"        # no reconciling total
    v = verdict(res, "party")
    assert v["bucket"] == "AMBER" and v["reason_code"] == "CORE_FIELD_EMPTY", v
    assert "Extraction is correct" not in v["reason"], v["reason"]
    assert "verify the column mapping" in v["reason"], v["reason"]


def test_low_master_match_is_amber():
    rows = stock_rows()
    for i, r in enumerate(rows):
        r["product_name"] = f"ZZZ UNKNOWN ITEM {i}"  # won't match catalog
    res = stock_result()
    res["rows"] = rows
    b, code = bucket(res, "stock")
    # only assert master logic when a catalog is present to compare against
    if _HAVE_CATALOG:
        assert b == "AMBER" and code == "LOW_MASTER_MATCH"
    else:
        assert b in ("AMBER", "GREEN")


def test_duplicate_rows_is_amber():
    rows = stock_rows(n=20)
    dup = dict(rows[0])
    res = stock_result()
    res["rows"] = [dict(dup) for _ in range(20)]  # all identical
    b, code = bucket(res, "stock")
    assert b == "AMBER" and code in ("DUPLICATE_ROWS", "CONSTANT_COLUMN")


def cosmo_style_result(mismatch_rows=5, n=20):
    """COSMO 'Stock sales statement Small' shape: per-unit Rate + quantity columns,
    NO per-row value column, and a printed rupee grand total the vendor computed as
    Σ rate×closing. `mismatch_rows` rows carry the vendor's own +5 closing surplus
    (free/scheme goods added to closing with no receipt), so quantity reconciliation
    fails on them while the extraction is byte-faithful."""
    rows = []
    rate_total = 0.0
    for i in range(n):
        op, pur, sal = 10 + i, 5 + (i % 3), 7 + (i % 4)
        cl = op + pur - sal + (5 if i < mismatch_rows else 0)
        rate = 100.0 + i
        rate_total += rate * cl
        rows.append({
            "product_name": _name(i), "pack": "10",
            "opening_stock": str(op), "purchase_stock": str(pur),
            "purchase_free": "0", "purchase_return": "0",
            "sales_qty": str(sal), "sales_value": "0",
            "sales_free": "0", "sales_return": "0",
            "closing_stock": str(cl), "closing_stock_value": "0",
            "rate": str(rate),
            "vendor_name": "ACME", "report_start_date": "2026-05-01",
            "report_end_date": "2026-05-31", "division": "COSMO",
        })
    return {
        "rows": rows,
        "headers_detected": {"Product Name": "product_name", "Rate": "rate",
                             "Opening": "opening_stock", "Reciept": "purchase_stock",
                             "Sales": "sales_qty", "Closing": "closing_stock"},
        "raw_text": ("stock sales statement small for the period\n"
                     + "\n".join(f"{r['product_name']} 10 {r['rate']} {r['opening_stock']} "
                                 f"{r['purchase_stock']} {r['sales_qty']} {r['closing_stock']}"
                                 for r in rows)
                     + f"\nGrand Total : {round(rate_total, 2)}\n"),
        "warnings": [],
        "sanity": {"pass_rate": (n - mismatch_rows) / n},
    }


def test_cosmo_rate_qty_proof_downgrades_red_to_amber():
    # The COSMO false-RED: quantity reconcile fails on 25% of rows (vendor's own
    # surplus), no per-row value column exists, but Σ rate×closing matches the
    # printed rupee grand total — proof the columns are mapped right. Must land
    # AMBER SANITY_VALUE_OK leading with "Extraction is correct", never RED.
    v = verdict(cosmo_style_result(), "stock")
    assert v["bucket"] == "AMBER" and v["reason_code"] == "SANITY_VALUE_OK", v
    assert v["reason"].startswith("Extraction is correct"), v["reason"]
    assert v["extraction_ok"] is True, v
    # both percentages present: extraction % and the vendor data-mismatch %
    assert "25%" in v["reason"], v["reason"]


def test_cosmo_without_printed_total_stays_red():
    # Same file WITHOUT the printed grand total: no proof -> the quantity failure
    # keeps its RED (a genuine misalignment must never be whitewashed).
    res = cosmo_style_result()
    res["raw_text"] = res["raw_text"].rsplit("Grand Total", 1)[0]
    v = verdict(res, "stock")
    assert v["bucket"] == "RED" and v["reason_code"] == "SANITY_FAILED", v
    assert v["reason"].startswith("Extraction is NOT correct"), v["reason"]
    assert v["extraction_ok"] is False, v


# --------------------------------------------------------------------------- #
# row completeness — the census behind "all N of N rows captured"
# --------------------------------------------------------------------------- #
def party_result_with_grid_text(extra_lines=0):
    """Party rows plus a raw_text grid carrying one census-visible line per row,
    plus `extra_lines` product-looking lines that match NO extracted row."""
    res = party_result()
    lines = ["party wise sales register"]
    for r in res["rows"]:
        lines.append(f"{r['product_name']} {r['qty']} {r['rate']} {r['taxable_value']}")
    for i in range(extra_lines):
        lines.append(f"ZZGHOSTLINE UNCAPTURED {i} 99 123.45")
    res["raw_text"] = "\n".join(lines)
    return res


def test_census_complete_claims_all_rows():
    res = party_result_with_grid_text()
    q = build_quality(res, "party")
    rc = q["checks"]["row_completeness"]
    assert rc["expected"] == 15 and rc["matched"] == 15, rc
    assert "all 15 of 15" in q["triage"]["reason"], q["triage"]["reason"]


def test_census_gap_never_alarms_or_claims():
    # A census gap is noise far more often than a real drop (measured on the
    # standing corpus: 365 flagged files, ALL noise — addresses/footers/banners),
    # so it must neither flip the verdict nor put a scary partial % in the
    # message. The gap data stays in checks["row_completeness"] for auditors;
    # a real drop is still caught by TOTAL_MISMATCH via the printed total.
    res = party_result_with_grid_text(extra_lines=4)  # 4 of 19 lines unmatched
    q = build_quality(res, "party")
    v = q["triage"]
    assert v["reason_code"] != "MISSING_ROWS", v
    assert "all 15 of 15" not in v["reason"], v["reason"]
    assert "% —" not in v["reason"].split(".")[1] if "Extraction:" in v["reason"] else True
    rc = q["checks"]["row_completeness"]
    assert rc["expected"] == 19 and rc["matched"] == 15, rc  # data kept for audits


def test_census_gap_with_total_proof_still_confirms_completeness():
    # The printed grand total matches our summed amounts -> mathematically no
    # value-carrying row was dropped; the 4 unmatched lines are census noise and
    # the message may still confirm nothing is missing.
    res = party_result_with_grid_text(extra_lines=4)
    total = sum(float(r["taxable_value"]) for r in res["rows"])
    res["raw_text"] += f"\nGrand Total : {total:.2f}"
    v = verdict(res, "party")
    assert v["reason_code"] != "MISSING_ROWS", v
    assert "printed grand total" in v["reason"], v["reason"]
    # HONEST claim: the printed-total proof covers only value-bearing rows (a dropped
    # zero-value row is invisible to the total), so the message must NOT over-claim
    # "no data row is missing" — it says "no value-bearing row is missing".
    assert "no value-bearing row is missing" in v["reason"], v["reason"]
    assert "no data row is missing" not in v["reason"], v["reason"]


# --------------------------------------------------------------------------- #
# extraction_ok — the machine-readable verdict driving the 4-state badge
# --------------------------------------------------------------------------- #
def test_extraction_ok_none_on_unproven_amber():
    res = party_result(party_value_mostly_zero_rows())  # partial column, no proof
    res["raw_text"] = "party wise sales register"
    v = verdict(res, "party")
    assert v["bucket"] == "AMBER" and v["extraction_ok"] is None, v
    assert v["reason"].startswith("Extraction needs a quick check"), v["reason"]


def test_extraction_ok_false_on_red():
    v = verdict({"rows": [], "headers_detected": {}, "raw_text": "", "warnings": []}, "stock")
    assert v["bucket"] == "RED" and v["extraction_ok"] is False, v
    assert v["reason"].startswith("Extraction is NOT correct"), v["reason"]


# --------------------------------------------------------------------------- #
# GREEN — clean extraction (needs a catalog to clear the master gate)
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(not _HAVE_CATALOG, reason="product_master catalog unavailable")
def test_clean_stock_is_green():
    b, code = bucket(stock_result(), "stock")
    assert b == "GREEN" and code == "CLEAN"


@pytest.mark.skipif(not _HAVE_CATALOG, reason="product_master catalog unavailable")
def test_green_says_extraction_correct():
    v = verdict(stock_result(), "stock")
    assert v["bucket"] == "GREEN" and v["reason_code"] == "CLEAN", v
    assert v["reason"].startswith("Extraction is correct"), v["reason"]
    assert v["extraction_ok"] is True, v


@pytest.mark.skipif(not _HAVE_CATALOG, reason="product_master catalog unavailable")
def test_clean_party_is_green():
    b, code = bucket(party_result(), "party")
    assert b == "GREEN" and code == "CLEAN"


def _lossy_line_audit():
    return {
        "applicable": True,
        "counts": {"lines": 260, "noise": 5, "total": 3, "context": 2,
                   "context_unclaimed": 0, "data": 200, "claimed": 150,
                   "unexplained": 50},
        "unexplained_ratio": 0.25,
        "unexplained_sample": ["DROPPED 5.00AB123 SZ1 09-05-26 5. 123.45X"],
    }


def test_unaccounted_lines_shadow_by_default():
    """Gate default is SHADOW: a lossy ledger must not change the verdict."""
    import core.triage as T
    res = party_result()
    res["line_audit"] = _lossy_line_audit()
    old = T._LEDGER_GATE
    T._LEDGER_GATE = False
    try:
        b, code = bucket(res, "party")
    finally:
        T._LEDGER_GATE = old
    assert code != "UNACCOUNTED_LINES"


def test_unaccounted_lines_fires_when_gated():
    """With the gate on, unexplained source lines cap the verdict at AMBER
    UNACCOUNTED_LINES with extraction_ok=None (never 'Extraction is correct')."""
    import core.triage as T
    res = party_result()
    res["line_audit"] = _lossy_line_audit()
    old = T._LEDGER_GATE
    T._LEDGER_GATE = True
    try:
        v = verdict(res, "party")
    finally:
        T._LEDGER_GATE = old
    assert v["bucket"] == "AMBER"
    assert v["reason_code"] == "UNACCOUNTED_LINES"
    assert v["extraction_ok"] is None
    assert not v["reason"].startswith("Extraction is correct")


def test_unaccounted_lines_quiet_below_thresholds():
    """A handful of unexplained lines (below min_lines/ratio) never fires."""
    import core.triage as T
    res = party_result()
    la = _lossy_line_audit()
    la["counts"]["unexplained"] = 2
    la["unexplained_ratio"] = 0.01
    res["line_audit"] = la
    old = T._LEDGER_GATE
    T._LEDGER_GATE = True
    try:
        b, code = bucket(res, "party")
    finally:
        T._LEDGER_GATE = old
    assert code != "UNACCOUNTED_LINES"


if __name__ == "__main__":
    # Standalone runner (no pytest needed): run every test_* function.
    import inspect

    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and inspect.isfunction(v)]
    passed = failed = skipped = 0
    for fn in fns:
        skip = getattr(fn, "__skip__", (False, ""))
        if skip[0]:
            print(f"SKIP {fn.__name__} ({skip[1]})")
            skipped += 1
            continue
        try:
            fn()
            print(f"PASS {fn.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL {fn.__name__}: {e}")
            failed += 1
        except Exception as e:  # noqa
            print(f"ERROR {fn.__name__}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed, {skipped} skipped")
    raise SystemExit(1 if failed else 0)
