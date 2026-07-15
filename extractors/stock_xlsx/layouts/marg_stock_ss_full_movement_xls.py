"""Marg (ERP 9+) "STOCK & SALES ANALYSIS" FULL movement GRID — SHAH ENTERPRISES .XLS.

This is the wide-movement sibling of ``marg_stock_analysis_qv_grid``: the same Marg "STOCK &
SALES ANALYSIS" report, division-banded (KLM COSMO / KLM DERMA / KLM PEDIA ...), but the full
7-movement-column form printed with a BLANK spacer column between most logical columns, and a
trailing STOCK Rate / STOCK Value pair. Two-row header (physical columns, 0-based)::

    (row A) ITEM NAME | OPENING | PURCHASE |   | FREE  | TOTAL | SALES   |   | FREE  |   | BALANCE |   | STOCK |   | STOCK
    (row B)           |         | -PurRet  |   | +Repl |       | -Return |   | +Repl |   | Stock   |   | Rate  |   | Value

so the physical columns are::

    col0  ITEM NAME       -> product_name (trailing pack token peeled, e.g. "... 15GM")
    col1  OPENING         -> opening_stock
    col2  PURCHASE-PurRet -> purchase_stock  (net purchase; -PurRet already folded in by ERP)
    col3  (blank spacer)
    col4  FREE +Repl      -> purchase_free   (inward free/replacement)
    col5  TOTAL           -> total_stock     (= opening+purchase+free, informational)
    col6  SALES -Return   -> sales_qty       (net sale; -Return already folded in by ERP)
    col7  (blank spacer)
    col8  FREE +Repl      -> sales_free       (outward free/replacement)
    col9  (blank spacer)
    col10 BALANCE Stock   -> closing_stock    (closing QTY)
    col11 (blank spacer)
    col12 STOCK Rate      -> rate
    col13 (blank spacer)
    col14 STOCK Value     -> closing_stock_value  (closing VALUE)  <-- the field the generic
                                                   tabular reader loses -> closing_val==0 -> RED

``closing_stock = opening + purchase + purchase_free - sales - sales_free`` on every row.

The book appends an unrelated ``PURCHASE DETAIL :-`` supplier ledger (SUPPLIER NAME | INVOICE ...
| AMOUNT — SHORT 7-cell rows whose col0 is a party like "AMIT PHARMA INDORE"), carries per-division
VALUE subtotal rows (col0 BLANK, ~11 cells), division bands (col0-only, 1 cell) and a MARG footer.
The generic ``tabular`` reader mis-mapped the STOCK Value column to nothing (closing value read 0)
AND leaked the 22 appended ledger rows as products with the rupee AMOUNT landing in ``sales_qty``
("some party missing"). We read POSITIONALLY and gate on a real product = a 15-cell row with a
non-blank col0 name and a numeric-or-nil OPENING(col1) and BALANCE(col10). Every band, subtotal,
ledger row and footer fails that gate and is dropped.
"""
import re

from extractors.stock_xlsx.constants import SUBTOTAL_RE
from extractors.stock_xlsx.parse_common import cell_text

_NUM_RE = re.compile(r"^-?\d[\d,]*(?:\.\d+)?$")

# Fixed positional column map (0-based) for the 15-column grid.
_ITEM = 0
_OPEN = 1
_PURCH = 2
_PFREE = 4
_TOTAL = 5
_SALES = 6
_SFREE = 8
_BAL = 10
_RATE = 12
_VALUE = 14
_MIN_WIDTH = 15


def _num_or_nil(tok):
    """Clean numeric string for a qty/value cell, or None if not a number.
    Bare '-' means nil -> '0'."""
    tok = (tok or "").strip()
    if not tok:
        return None
    if set(tok) == {"-"}:
        return "0"
    if _NUM_RE.match(tok):
        return tok.replace(",", "")
    return None


def _split_name_pack(text):
    """Peel the trailing pack token (last whitespace token) unless it is a bare number."""
    toks = text.split()
    if len(toks) <= 1:
        return text, ""
    if _NUM_RE.match(toks[-1]):
        return text, ""
    return " ".join(toks[:-1]), toks[-1]


def parse_marg_stock_ss_full_movement_xls(rows):
    # Locate the header row: col0 == 'ITEM NAME'.
    header_idx = None
    for idx in range(min(len(rows), 60)):
        first = cell_text(rows[idx][0]) if rows[idx] else ""
        if first.strip().lower().replace(" ", "") == "itemname":
            header_idx = idx
            break
    if header_idx is None:
        return [], {}

    records = []
    for raw_row in rows[header_idx + 1:]:
        cells = [cell_text(c) for c in raw_row] if raw_row else []
        if len(cells) < _MIN_WIDTH:
            continue  # short line: band (1 cell), subtotal (~11), supplier ledger (7)
        name_cell = cells[_ITEM].strip()
        if not name_cell or SUBTOTAL_RE.match(name_cell):
            continue
        low = name_cell.lower().replace(" ", "")
        if low == "itemname" or low.startswith("suppliername"):
            continue  # repeated page header / start of appended supplier ledger

        # Structural gate: a real product prints a numeric (or bare-dash nil) OPENING and
        # BALANCE quantity. Bands, subtotal rows (blank col0), the supplier ledger and the
        # footer all fail this and are dropped.
        opening = _num_or_nil(cells[_OPEN])
        closing = _num_or_nil(cells[_BAL])
        if opening is None or closing is None:
            continue

        name, pack = _split_name_pack(name_cell)
        record = {
            "product_name": name,
            "pack": pack,
            "opening_stock": opening,
            "purchase_stock": _num_or_nil(cells[_PURCH]) or "0",
            "purchase_free": _num_or_nil(cells[_PFREE]) or "0",
            "total_stock": _num_or_nil(cells[_TOTAL]) or "0",
            "sales_qty": _num_or_nil(cells[_SALES]) or "0",
            "sales_free": _num_or_nil(cells[_SFREE]) or "0",
            "closing_stock": closing,
            "rate": _num_or_nil(cells[_RATE]) or "0",
            "closing_stock_value": _num_or_nil(cells[_VALUE]) or "0",
        }
        records.append(record)

    detected = {
        "ITEM NAME": "product_name",
        "OPENING": "opening_stock",
        "PURCHASE -PurRet": "purchase_stock",
        "FREE +Repl (in)": "purchase_free",
        "TOTAL": "total_stock",
        "SALES -Return": "sales_qty",
        "FREE +Repl (out)": "sales_free",
        "BALANCE Stock": "closing_stock",
        "STOCK Rate": "rate",
        "STOCK Value": "closing_stock_value",
    }
    return records, detected
