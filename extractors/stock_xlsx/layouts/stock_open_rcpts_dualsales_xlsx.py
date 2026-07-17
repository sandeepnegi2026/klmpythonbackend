"""KLM LABORATORIES stock statement — "Open.Stk / Rcpts / L.Sales / Cur.Sls." export.

The .xlsx twin of the stock_pdf ``stock_open_pur_sale_free_current`` KLM family
(SAI PHARMA AGENCIES). Single-band, one row per product. The printed header has
NINE cells::

    Item Name | Packg | Open.Stk. | Rcpts | L.Sales | Cur.Sls. | Pur.Rtn. | Sls.Rtn. | Clos.(Qty & Amt)

but every DATA row carries TEN physical columns — the trailing "Clos.(Qty & Amt)"
header spans two cells: closing QTY then closing VALUE. So the generic tabular
reader (which maps by the 9-cell header) mis-reads closing_stock <- the closing
VALUE (a rupee figure) and every row fails the sanity equation.

This parser maps by POSITION off the 10 physical data columns:

    0 name | 1 pack | 2 opening | 3 receipts | 4 L.Sales | 5 Cur.Sls |
    6 Pur.Rtn | 7 Sls.Rtn | 8 closing QTY | 9 closing VALUE

Sales columns: **only Cur.Sls. (current-month sales) reduces the closing stock.**
L.Sales is the PRIOR-month sales figure printed for reference and is NOT part of the
current-period movement — verified empirically: ``closing = opening + receipts -
Cur.Sls.`` reconciles on 84/85 non-zero rows, whereas subtracting L.Sales as well
reconciles on only 42. So ``sales_qty`` = Cur.Sls. alone; L.Sales is preserved in the
non-canonical ``prior_sales_qty`` field so it never corrupts the sanity equation.
Pur.Rtn / Sls.Rtn stay in the return fields. There are no free-qty columns.

Reconciles exactly, e.g. APPYBUSH 50 + 0 - 42 = 8 (printed closing qty 8, value 858);
CUTIHEAL 25 + 5 - 4 = 26 (L.Sales 20 ignored); CETALORE M 86 + 0 - 0 = 86 (value 5229).
"""
from extractors.stock_xlsx.parse_common import cell_text

# Compact (space-stripped, lowercased) tokens that MUST all appear across the header
# region for this layout. This abbreviation set — Rcpts + L.Sales + Cur.Sls. + the
# combined "Clos.(Qty & Amt)" — is unique to this KLM export.
_HEADER_TOKENS = ("open.stk.", "rcpts", "l.sales", "cur.sls.", "clos.(qty")

_SKIP_PREFIXES = (
    "grand total", "total", "item name", "division", "company",
    "stock report", "opening value", "closing value",
)


def _num(cell):
    s = cell_text(cell).strip().replace(",", "")
    if s in ("", "-"):
        return 0.0
    try:
        return float(s)
    except ValueError:
        return None


def _find_header(rows):
    """Locate the header row: the first row whose compact-joined cells carry all of the
    distinctive KLM abbreviations."""
    for idx, row in enumerate(rows[:25]):
        flat = "".join(cell_text(c) for c in row).lower().replace(" ", "")
        if all(tok in flat for tok in _HEADER_TOKENS):
            return idx
    return None


def _as_str(val):
    return str(int(val)) if val == int(val) else str(val)


def parse_stock_open_rcpts_dualsales_xlsx(rows):
    header_idx = _find_header(rows)
    if header_idx is None:
        return [], {}

    records = []
    for raw in rows[header_idx + 1:]:
        cells = [cell_text(c) for c in raw]
        if not cells:
            continue
        product = cells[0].strip()
        low = product.lower()
        if not product or low.startswith(_SKIP_PREFIXES):
            continue
        # A genuine data row has 10 physical columns (name, pack, 8 numbers incl. the
        # split closing qty/value). The Grand Total footer has only 9 (no closing value
        # cell) and is caught by the prefix skip above; guard the width anyway.
        if len(cells) < 10:
            continue

        pack = cells[1].strip()
        nums = [_num(c) for c in cells[2:10]]
        if any(n is None for n in nums):  # a stray non-numeric cell -> not a data row
            continue
        opening, receipts, l_sales, cur_sls, pur_rtn, sls_rtn, clos_qty, clos_val = nums

        record = {
            "product_name": product,
            "pack": pack,
            "opening_stock": _as_str(opening),
            "purchase_stock": _as_str(receipts),
            # Only current-month sales reduce closing stock (see module docstring).
            "sales_qty": _as_str(cur_sls),
            "purchase_return": _as_str(pur_rtn),
            "sales_return": _as_str(sls_rtn),
            "closing_stock": _as_str(clos_qty),          # the QTY, 2nd-to-last cell
            "closing_stock_value": _as_str(clos_val),    # the VALUE, last cell
        }
        # Prior-month sales — informational only, kept off the reconcile fields.
        if l_sales:
            record["prior_sales_qty"] = _as_str(l_sales)
        records.append(record)

    detected = {
        "Item Name": "product_name",
        "Packg": "pack",
        "Open.Stk.": "opening_stock",
        "Rcpts": "purchase_stock",
        "Cur.Sls.": "sales_qty",
        "L.Sales": "prior_sales_qty",
        "Pur.Rtn.": "purchase_return",
        "Sls.Rtn.": "sales_return",
        "Clos. Qty": "closing_stock",
        "Clos. Amt": "closing_stock_value",
    }
    return records, detected
