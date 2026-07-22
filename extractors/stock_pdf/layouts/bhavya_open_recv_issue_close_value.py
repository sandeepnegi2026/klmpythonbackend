"""BHAVYA MEDICAL AGENCIES 'Stock & Sales' — Opening/Received/Issued/Closing qty + Value.

Header (3 wrapped lines):
    Opening Received Issued Closing
    Item Name
    Pack Qty Qty Qty Qty Value

Columns: Item Name | Pack | Opening(qty) | Received(qty) | Issued(qty) | Closing(qty) | Value(₹)

The four qty cells are RIGHT-ALIGNED and BLANK when zero, so a flat text row shows
only the 2-4 non-zero qty numbers followed by the trailing rupee Value (Indian
thousands commas, e.g. '5,616.00'). The generic/simple4 route mis-handles this two
ways: (1) it has no Value column so it dumps the rupee Value into closing_stock, and
(2) the comma-blind number walk halts at the first comma value and drops most rows.

This dedicated parser instead: peels the LAST number as the rupee Value, the last
remaining qty as Closing, and binds the preceding qty numbers to opening/received/
issued using the reconcile identity  opening + received - issued == closing  (the
only reliable disambiguator once the blank cells are gone). Reaching this parser at
all requires the BHAVYA-unique detect gate, so it can never touch another layout.
"""
import re

from extractors.stock_pdf.parse_common import (
    _nums,
    _split_product_numbers_comma as _split_product_numbers,
    _split_product_pack,
)

# Header / value-summary / band lines that are not product rows.
_SKIP_SUBSTR = (
    "bhavya medical",
    "stock & sales",
    "opening value",
    "received value",
    "value issued",
    "closing value",
    "opening received issued closing",
    "item name",
    "pack qty",
    "d.no",
)


def _bind(rem, closing):
    """Bind the qty numbers BEFORE closing to (opening, received, issued).

    `rem` holds 0-3 present qty numbers (the closing qty already peeled). Blank
    cells are gone, so we choose the placement satisfying opening+received-issued
    == closing. Ambiguous no-movement rows default to opening (never affects the
    closing/value fields, which are the point of this parser)."""
    if len(rem) >= 3:
        o, r, i = rem[0], rem[1], rem[2]
        return o, r, i
    if len(rem) == 2:
        a, b = rem[0], rem[1]
        for o, r, i in ((a, b, 0.0), (a, 0.0, b), (0.0, a, b)):
            if abs((o + r - i) - closing) < 0.5:
                return o, r, i
        return a, b, 0.0
    if len(rem) == 1:
        a = rem[0]
        if abs(a - closing) < 0.5:      # opening == closing, no movement
            return a, 0.0, 0.0
        if abs(a - closing) < abs(0.0 - closing):  # received drives closing
            return 0.0, a, 0.0
        return a, 0.0, 0.0
    return closing, 0.0, 0.0            # only closing present -> opening = closing


def parse_bhavya_open_recv_issue_close_value(text):
    records = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        low = s.lower()
        if any(k in low for k in _SKIP_SUBSTR):
            continue
        if low.startswith("total"):          # 'Total 22,153.77' footer
            continue
        prod, tail, exp = _split_product_numbers(s)
        if not prod or not re.search(r"[A-Za-z]{3}", prod):
            continue
        vals = _nums(tail)
        if len(vals) < 2:                     # need at least closing + value
            continue
        name, pack = _split_product_pack(prod)
        value = vals[-1]                       # trailing rupee Value
        qtys = vals[:-1]                       # 1-4 qty numbers
        closing = qtys[-1]
        opening, received, issued = _bind(qtys[:-1], closing)
        r = {
            "product_name": name,
            "pack": pack,
            "opening_stock": opening,
            "purchase_stock": received,
            "sales_qty": issued,
            "closing_stock": closing,
            "closing_stock_value": value,
        }
        if exp:
            r["expiry"] = exp
        records.append(r)
    return records
