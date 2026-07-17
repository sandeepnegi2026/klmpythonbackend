import re

from extractors.stock_pdf.constants import SKIP_RE, SUBTOTAL_RE
from extractors.stock_pdf.parse_common import (
    _nums,
    _split_product_numbers,
    _split_product_pack,
)


def _skip(s):
    """Local skip for this layout.

    Deliberately does NOT reuse parse_common._skip_line: that helper drops every
    line starting with "KLM " to filter the division BANDS (KLM BABY, KLM COSMO,
    ...), but this vendor also sells KLM-branded PRODUCTS (KLM KLIN FACE WASH,
    KLM C 1000, KLM FX-180 TAB, ...) whose rows would then be lost. Here the
    division bands are separated structurally instead — they carry no trailing
    numbers and fail the len(tail) == 9 gate below — so the "KLM " clause is
    intentionally omitted and the SUBTOTAL/SKIP header filters are kept.
    """
    if not s or len(s) < 5:
        return True
    if SUBTOTAL_RE.match(s) or SKIP_RE.match(s):
        return True
    if re.match(r"^[\d\s\-]+$", s):
        return True
    return False


def parse_qty_value_total(text):
    """Qty+Value pairs with a standalone Total column.

    Layout (e.g. "Sales & Stock Statement" exports, division-banded):
        PRODUCT [PACK]
        OPEN_QTY OPEN_VAL  RECEIPT_QTY RECEIPT_VAL  TOTAL_QTY
        ISSUE_QTY ISSUE_VAL  CLOSE_QTY CLOSE_VAL

    i.e. exactly 9 numbers per row, where Receipt == Purchase and Issue == Sales.
    Differs from value_pairs (4 clean qty/value pairs = 8 numbers) by the extra
    standalone TOTAL_QTY column (= opening + receipt) between receipt and issue.
    """
    # Two extended tails, each gated on a header token unique to its export so no
    # existing 8/9-number file changes:
    #   10 numbers — GEETA appends a NEAR-EXPIRY count after Closing (drop vals[9]).
    #   11/12 numbers — SIDDHI appends Dump Stock + MSR Price (drop vals[9], vals[10];
    #     a 12-tail carries a stray name digit, so take the LAST 11).
    low = text.lower()
    _c = low.replace(" ", "")
    has_near = "closingbalanear" in _c or "nearexp" in _c or "n.e.value" in _c
    has_dump_msr = "dump" in _c and "msr" in _c

    records = []
    for line in text.splitlines():
        s = line.strip()
        if _skip(s):
            continue
        prod, tail, exp = _split_product_numbers(s)
        # Structural lock: only rows carrying the movement numbers — 9 for the
        # standalone-TOTAL_QTY export, or 8 for the ZISHAN "Sales & Stock
        # Statement" sibling (4 qty/value pairs; its pair-2 value is the running
        # TOTAL value = opening_val + receipt_val, so purchase_value is not
        # emitted there). Bands/furniture carry no trailing numbers and drop out.
        if not prod or len(tail) not in (8, 9, 10, 11, 12):
            continue
        name, pack = _split_product_pack(prod)
        vals = _nums(tail)
        if len(vals) == 10 and has_near:
            # OpQ OpV RcptQ RcptV TotalQ IssQ IssV ClosQ ClosV NearExp -> map first 9.
            vals = vals[:9]
        elif len(vals) in (11, 12) and has_dump_msr:
            # ...ClosQ ClosV Dump MSR (12: stray glued name digit leads) -> LAST 11,
            # then keep the 9 movement numbers (drop Dump vals[9] and MSR vals[10]).
            vals = vals[-11:][:9]
        if len(vals) == 9:
            r = {
                "product_name": name,
                "pack": pack,
                "opening_stock": vals[0],
                "opening_value": vals[1],
                "purchase_stock": vals[2],
                "purchase_value": vals[3],
                "total_stock": vals[4],
                "sales_qty": vals[5],
                "sales_value": vals[6],
                "closing_stock": vals[7],
                "closing_stock_value": vals[8],
            }
        elif len(vals) == 8:
            # OP q/v | Receipt qty + TOTAL value | Issue q/v | Closing q/v.
            # Verified: Closing = OP + Receipt - Issue on every reference row
            # (EKRAN SOFT: 24+98-122=0; HISTABIL M: 10+0-0=10) and the report's
            # own TOTAL line (401+535-926=10).
            r = {
                "product_name": name,
                "pack": pack,
                "opening_stock": vals[0],
                "opening_value": vals[1],
                "purchase_stock": vals[2],
                "sales_qty": vals[4],
                "sales_value": vals[5],
                "closing_stock": vals[6],
                "closing_stock_value": vals[7],
            }
        else:
            continue
        if exp:
            r["expiry"] = exp
        records.append(r)
    return records
