"""Tests for core/line_ledger.py — the "every source line must be explained" ledger.

The headline test reproduces the 2026-07-21 incident: marg_register silently
dropped 386/2068 item lines and triage said GREEN CLEAN. The ledger must flag
the pre-fix parser loudly (via a faithful inline copy of the pre-fix matcher)
and stay silent on the fixed one — using only value anchoring, never the
parser's own matcher.
"""
import io
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.line_ledger import (  # noqa: E402
    audit_sheet_rows,
    audit_text_lines,
    build_row_index,
    classify_line,
)

VENUS = os.path.join(
    os.path.dirname(ROOT), "..", "Final_Data",
    "VENUS PHARMA _Ahmedabad_", "Party report", "June_26 Partywise KLM.PDF",
)
VENUS = os.path.abspath(os.path.join(ROOT, "..", "..", "Final_Data",
                                     "VENUS PHARMA _Ahmedabad_", "Party report",
                                     "June_26 Partywise KLM.PDF"))


def _venus_text():
    import pdfplumber
    with open(VENUS, "rb") as fh:
        fb = fh.read()
    with pdfplumber.open(io.BytesIO(fb)) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages)


def _prefix_only_matcher(s):
    """Faithful inline copy of the four PRE-FIX primary patterns of
    _marg_register_item_match (everything above the glued-batch fallbacks),
    with the GST tightening applied to `glued` only as it shipped originally.
    """
    for pat in (
        r"^(.+?)\s+(\d+\.\d{2})([A-Z][A-Z0-9]+)\s+(\S+)\s+(\d{2}-\d{2}-\d{2})\s+(.+)$",
        r"^([\d.]+)\s+([A-Z][A-Z0-9]+)\s+(\S+)\s+(\d{2}-\d{2}-\d{2})\s+(.+)$",
        r"^([\d.]+)\s+(\S+)\s+(\d{2}-\d{2}-\d{2})\s+(.+)$",
        r"^(.+?)\s+([\d.]+)\s+([A-Z][A-Z0-9]+)\s+(\S+)\s+(\d{2}-\d{2}-\d{2})\s+(.+)$",
    ):
        m = re.match(pat, s)
        if m:
            g = m.groups()
            if len(g) == 6:
                return {"product": g[0].strip(), "gst": g[1], "batch": g[2],
                        "inv_no": g[3], "date": g[4], "tail": g[5]}
            if len(g) == 5:
                return {"product": "", "gst": g[0], "batch": g[1],
                        "inv_no": g[2], "date": g[3], "tail": g[4]}
            return {"product": "", "gst": g[0], "batch": "",
                    "inv_no": g[1], "date": g[2], "tail": g[3]}
    return None


# --------------------------------------------------------------------------- #
# VENUS sentinel — the incident, both sides
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(not os.path.exists(VENUS), reason="VENUS corpus file absent")
def test_venus_fixed_parser_zero_unexplained():
    from extractors.party_pdf.layouts.marg_register import parse_marg_register
    text = _venus_text()
    h, rows = parse_marg_register(text)
    la = audit_text_lines(text, rows, headers=h)
    assert la["applicable"]
    # <=5, not ==0: a few ZERO-AMOUNT free-goods lines (amount 0.00, whose only
    # distinctive numbers are a product-name digit or salesman phone, and whose
    # invoice-id is shared with kept siblings so it cannot safely claim) are a
    # known ledger blind spot. They are harmless — this file's printed totals
    # reconcile exactly, so the gate suppresses UNACCOUNTED_LINES regardless (see
    # test_venus_prefix_bug_flagged_loudly for the real-drop guarantee).
    assert la["counts"]["unexplained"] <= 5
    assert la["counts"]["data"] >= 2000


@pytest.mark.skipif(not os.path.exists(VENUS), reason="VENUS corpus file absent")
def test_venus_prefix_bug_flagged_loudly(monkeypatch):
    import extractors.party_pdf.layouts.marg_register as M
    text = _venus_text()
    monkeypatch.setattr(M, "_marg_register_item_match", _prefix_only_matcher)
    h, rows = M.parse_marg_register(text)
    la = audit_text_lines(text, rows, headers=h)
    # 386 lines were historically dropped; consumption claims must expose the
    # bulk of them (duplicate-amount surplus absorbs a few) and blow far past
    # the gate thresholds (>=5 lines, >=2% of data lines).
    assert la["counts"]["unexplained"] >= 250
    assert la["unexplained_ratio"] >= 0.05


@pytest.mark.skipif(not os.path.exists(VENUS), reason="VENUS corpus file absent")
def test_venus_deletion_sensitivity():
    """Deleting every 5th parsed row must surface as unexplained lines."""
    from extractors.party_pdf.layouts.marg_register import parse_marg_register
    text = _venus_text()
    h, rows = parse_marg_register(text)
    kept = [r for i, r in enumerate(rows) if i % 5]
    deleted = len(rows) - len(kept)
    la = audit_text_lines(text, kept, headers=h)
    assert la["counts"]["unexplained"] >= int(deleted * 0.5)


# --------------------------------------------------------------------------- #
# taxonomy units
# --------------------------------------------------------------------------- #
def test_classify_total_lines():
    assert classify_line("1. Invoice 1669 365 0.00 476336.46") == "total"
    assert classify_line("2. Credit Note -18 0 -638.91 -2617.48") == "total"
    assert classify_line("23171. 4657. -4911.27 3779318.97") == "total"
    assert classify_line("Grand Total   1234   99,077.75") == "total"


def test_classify_noise_lines():
    assert classify_line("Page 3 of 48") == "noise"
    assert classify_line("Report Date : 06-Jul-26 09:14:00 Page 48 of 48") == "noise"
    assert classify_line("Sales Detail Register (Mf-Customer-Itemwise) From date 01-06-26 to 30-06-26") == "noise"
    assert classify_line("Item GSTBatch InvNo. Date Qty S. Qty Disc % Sch Disc AmountSalesMan") == "noise"
    assert classify_line("GSTIN : 24AAAAA0000A1Z5") == "noise"


def test_classify_data_and_text():
    assert classify_line(
        "IMXIA XL SERUM 60ML(18%) 18.00BF3501 SZ3843 08-06-26 10. 10. 9627.10MAUNISH"
    ) == "data"
    assert classify_line("MF : XA0003 - KLM LABORATORIES-COSMETICS-85 [ KLM ]") == "text"
    assert classify_line("") == "blank"
    assert classify_line("-----------------") == "blank"


def test_wrapped_row_halves_are_explained():
    """One row printed across two lines: number half claims by value, name half
    is context via the row's text."""
    rows = [{"product_name": "KOJITIN ULTRA EMULGEL", "qty": "20", "amount": "8088.83"}]
    text = "KOJITIN ULTRA\nEMULGEL 20. 8088.83\n"
    la = audit_text_lines(text, rows)
    assert la["counts"]["unexplained"] == 0


def test_duplicate_amounts_cannot_hide_drops():
    """Two identical-amount lines but only ONE emitted row: consumption must
    flag the second line instead of letting the twin cover it."""
    rows = [{"product_name": "EKRAN GEL", "qty": "5", "amount": "1452.36"}]
    text = ("EKRAN GEL 5. 1452.36\n"
            "EKRAN GEL 5. 1452.36\n")
    la = audit_text_lines(text, rows)
    assert la["counts"]["unexplained"] == 1


def test_page_repeated_report_not_flagged():
    """A report whose extracted text repeats the ENTIRE page N times (a common
    Marg/print artifact — manufacturerwise_billwise ships 10 identical pages) must
    NOT count the repeats as dropped rows. The parser emits one copy; the ledger
    de-dupes exact repeats at scale and audits a single copy."""
    header = ("Manufacturerwise Sales Report\n"
              "Bill Date Bill No Product Name Qty Gross\n")
    body = "".join(
        f"1{i:02d}/05/26 26D010{i:05d} PRODUCT {i} 2 {100 + i}.50\n"
        for i in range(40)
    )
    page = header + body
    text = page * 6  # 6 identical printed pages
    rows = [{"product_name": f"PRODUCT {i}", "qty": "2", "amount": f"{100 + i}.50"}
            for i in range(40)]
    la = audit_text_lines(text, rows)
    assert la["applicable"]
    # one copy's worth of data lines, all claimed; the 5 repeated copies vanish.
    assert la["counts"]["unexplained"] == 0
    assert la["counts"]["data"] <= 45


def test_party_header_does_not_consume_amount():
    """Single-item party: header total == item amount. Header must claim via
    party-text context, leaving the amount slot for the item line."""
    headers = ["Party Name", "Area", "Item Name", "Qty", "Amount"]
    rows = [["AAKASH MEDICINES (VASTRAPUR)", "AHMEDABAD", "IMXIA XL SERUM", "10", "9627.10"]]
    text = ("AAKASH MEDICINES (VASTRAPUR), AHMEDABAD 3750 VASTRAPUR- 731 0.00 9627.10\n"
            "IMXIA XL SERUM 18.00BF3501 SZ3843 08-06-26 10. 9627.10\n")
    la = audit_text_lines(text, rows, headers=headers)
    assert la["counts"]["unexplained"] == 0


def test_zero_movement_stock_row_claimed_by_name():
    """Stock statement (unique products, value-bearing): a zero-movement product
    row (every column 0/dash + a trailing MRP/rate integer) is genuinely
    extracted, so it must be CLAIMED by its product name — not left UNEXPLAINED.
    Reproduces the stock_qoh / profit_maker / marg_ss FP cluster: names carrying
    embedded digits ('EKRAN 80', 'ZITLIN 250', 'KLM C 20') that the old
    digit-dropping tokenizer could not match."""
    rows = [
        {"product_name": "EKRAN 80 HYDRAGEL SUNSCREEN 50GM", "closing_value": "982.81"},
        {"product_name": "IMXIA 10 60ML", "closing_value": "1450.00"},
        {"product_name": "ZITLIN 250 TAB 10S", "closing_value": "755.25"},
        {"product_name": "KLM C 20 GEL 20GM", "closing_value": "0"},  # zero-movement
    ]
    text = ("EKRAN 80 HYDRAGEL SUNSCREEN 50GM 3 0 0 3 0 982.81 348\n"
            "IMXIA 10 60ML 5 0 2 3 0 1450.00 257\n"
            "ZITLIN 250 TAB 10S 4 0 1 3 0 755.25 251\n"
            "KLM C 20 GEL 20GM 0 0 0 0 0 0.00 727\n")
    la = audit_text_lines(text, rows)
    assert la["applicable"]
    assert la["counts"]["unexplained"] == 0


def test_dropped_sibling_size_still_flagged():
    """The safety property behind the zero-movement claim: preserving digits keeps
    sibling strengths/sizes distinct, so a genuinely DROPPED 'EKRAN 80' (no
    record) is NOT claimed by the kept 'EKRAN 30' — it stays UNEXPLAINED. A loose
    digit-dropping matcher would have hidden it (both collapse to 'EKRAN')."""
    rows = [
        {"product_name": "EKRAN 30 SILICON SUNSCREEN GEL 30G", "closing_value": "982.81"},
        {"product_name": "IMXIA 10 60ML", "closing_value": "1450.00"},
        {"product_name": "ZITLIN 250 TAB 10S", "closing_value": "755.25"},
    ]
    text = ("EKRAN 30 SILICON SUNSCREEN GEL 30G 3 0 0 3 0 982.81 348\n"
            "IMXIA 10 60ML 5 0 2 3 0 1450.00 257\n"
            "ZITLIN 250 TAB 10S 4 0 1 3 0 755.25 251\n"
            "EKRAN 80 HYDRAGEL SUNSCREEN 50GM 0 0 0 0 0 0.00 727\n")  # DROPPED
    la = audit_text_lines(text, rows)
    assert la["counts"]["unexplained"] == 1


def test_sheet_rows_accounting():
    records = [{"product_name": "ZYCOZOL CREAM", "qty": "30", "amount": "4682.26"}]
    sheets = [("Sheet1", [
        ["ZYCOZOL CREAM", 30, 4682.26],
        ["DROPPED PRODUCT", 7, 1234.56],
        [],
        ["Grand Total", "", 5916.82],
    ])]
    la = audit_sheet_rows(sheets, records)
    assert la["counts"]["unexplained"] == 1
    assert la["counts"]["total"] == 1


def test_inapplicable_paths():
    assert audit_text_lines("", [])["applicable"] is False
    assert audit_text_lines("x 1.00", [])["applicable"] is False  # zero rows
    la = audit_sheet_rows([], [])
    assert la["applicable"] is False


def test_row_index_shapes():
    idx = build_row_index([["A PARTY", "1,584.43", "AA3605"]],
                          headers=["Party Name", "Amount", "Batch"])
    assert "1584.43" in idx["nums"]
    assert "AA3605" in idx["ids"]
    assert any("APARTY" in t for t in idx["texts_party"])
