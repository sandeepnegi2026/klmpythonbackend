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
    records = []
    for line in text.splitlines():
        s = line.strip()
        if _skip(s):
            continue
        prod, tail, exp = _split_product_numbers(s)
        # Structural lock: only rows carrying exactly the 9 movement numbers.
        # This also drops the division bands (KLM BABY, ...) which carry none,
        # while keeping KLM-branded product rows which carry all nine.
        if not prod or len(tail) != 9:
            continue
        name, pack = _split_product_pack(prod)
        vals = _nums(tail)
        if len(vals) != 9:
            continue
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
        if exp:
            r["expiry"] = exp
        records.append(r)
    return records
