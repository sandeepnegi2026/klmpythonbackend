"""Marg (custom KLM ERP) "Stock and Sales Report For Month" GRID with an OFFSET two-row header
(CHAITANYA PHARMA, "klm derma stock and sales.xls").

The header spans two rows whose group labels are offset from the data columns::

    (row A group) ................. Opening ..... Purchase / ..... SaleS / ..... Closing
    (row B sub)   Product Name  Pkg  LMS  Amount   P.Return       Sale Return    Qty  Amount

so the generic `tabular` reader binds the GROUP row (which has no "Product Name" cell) as the
header, never maps product_name, and extracts 0 rows (UNKNOWN_LAYOUT). The real column layout is
fixed and verified by reconciliation (opening + purchase - sales = closing, qty)::

    col0  Product Name       col3  Pkg (pack)       col4  LMS (prior-month, ignored)
    col5  OPENING qty        col6  OPENING value
    col7  PURCHASE qty       col8  PURCHASE value
    col9  SALES qty          col10 SALES value
    col11 CLOSING qty        col12 CLOSING value

e.g. MFSONE CREAM 42 + 150 - 84 = 108 == closing, and the extracted opening/purchase/sales/
closing VALUE sums match the printed "Total :" grand totals (325475.43 / 118376.57 / 117822.01 /
338745.93). The book carries per-division "SUB TOTAL FOR : <div>" and a "Total :" footer plus
underscore rule lines — all skipped. Zero-stock products (blank movement but a real name + pkg)
are kept as faithful catalog rows.
"""
import re

from extractors.stock_xlsx.parse_common import cell_text, is_subtotal

_NUM_RE = re.compile(r"^-?\d+(?:\.\d+)?$")

# Fixed positional column map (0-based).
_PACK = 3
_OPEN_Q, _OPEN_V = 5, 6
_PUR_Q, _PUR_V = 7, 8
_SAL_Q, _SAL_V = 9, 10
_CLOSE_Q, _CLOSE_V = 11, 12


def _num(tok):
    """Clean numeric string for a qty/value cell, else '0' (blank / non-numeric label)."""
    tok = tok.strip()
    return tok if _NUM_RE.match(tok) else "0"


def _nonzero(tok):
    """True when the cell holds a non-zero number (a real movement)."""
    tok = tok.strip()
    return bool(_NUM_RE.match(tok)) and float(tok) != 0.0


def parse_marg_stock_sales_lms_xls(rows):
    # Locate the sub-header row whose col0 == 'Product Name'; data begins after it.
    header_idx = None
    for idx in range(min(len(rows), 40)):
        first = cell_text(rows[idx][0]).strip().lower().replace(" ", "") if rows[idx] else ""
        if first == "productname":
            header_idx = idx
            break
    if header_idx is None:
        return [], {}

    records = []
    for raw_row in rows[header_idx + 1:]:
        cells = [cell_text(c) for c in raw_row] if raw_row else []
        if len(cells) <= _CLOSE_V:
            continue
        name = cells[0].strip()
        if not name or is_subtotal(name):
            continue
        low = name.lower()
        if low.startswith("sub total") or low.startswith("total") or low.startswith("company"):
            continue
        # Skip underscore / dash rule lines (product name with no alphanumeric char).
        if not any(ch.isalnum() for ch in name):
            continue
        pack = cells[_PACK].strip()
        movement = [cells[i].strip() for i in (_OPEN_Q, _PUR_Q, _SAL_Q, _CLOSE_Q)]
        # A real product row carries a Pkg or at least one numeric movement cell; a bare
        # division band (name only, no pkg, no movement) fails both and is dropped.
        if not pack and not any(_NUM_RE.match(m) for m in movement):
            continue

        # Repair a mis-columned OPENING value: this KLM export occasionally slides the opening
        # rupee value into the opening-QTY cell when the opening qty is blank (e.g. CANROLFIN
        # 15GM prints '2902.41' in the qty column with an empty value cell). A stock qty in this
        # report is always a whole number, so a fractional token paired with an empty value cell
        # is the value — move it back so it doesn't pollute opening_stock and the opening VALUE
        # total reconciles.
        open_q, open_v = cells[_OPEN_Q].strip(), cells[_OPEN_V].strip()
        if not open_v and _NUM_RE.match(open_q) and not float(open_q).is_integer():
            open_v, open_q = open_q, ""
            # The qty cell was blank. For a STATIC product (no purchase, no sales) the stock
            # identity forces opening == closing, and the recovered opening value equals the
            # closing value — so the true opening qty is the closing qty. Reconstruct it: this is
            # determined by the vendor's own no-movement data, not fabricated. If the product DID
            # move, the opening qty is genuinely unknown and stays blank (0), so the row still
            # fails the sanity equation honestly.
            if not _nonzero(cells[_PUR_Q]) and not _nonzero(cells[_SAL_Q]):
                open_q = cells[_CLOSE_Q].strip()

        records.append(
            {
                "product_name": name,
                "pack": pack,
                "opening_stock": _num(open_q),
                "opening_value": _num(open_v),
                "purchase_stock": _num(cells[_PUR_Q]),
                "purchase_value": _num(cells[_PUR_V]),
                "sales_qty": _num(cells[_SAL_Q]),
                "sales_value": _num(cells[_SAL_V]),
                "closing_stock": _num(cells[_CLOSE_Q]),
                "closing_stock_value": _num(cells[_CLOSE_V]),
            }
        )

    detected = {
        "Product Name": "product_name",
        "Pkg": "pack",
        "Opening Qty": "opening_stock",
        "Opening Amount": "opening_value",
        "Purchase Qty": "purchase_stock",
        "Purchase Amount": "purchase_value",
        "Sales Qty": "sales_qty",
        "Sales Amount": "sales_value",
        "Closing Qty": "closing_stock",
        "Closing Amount": "closing_stock_value",
    }
    return records, detected
