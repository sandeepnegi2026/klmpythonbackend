"""Marg ERP9+ REDUCED "STOCK & SALES ANALYSIS" grid — 8-column positional (BALLRI).

BALLARI PHARMA DISTRIBUTORS (BHARATHI MEDI. AGENCY) exports a *reduced* Marg ERP9+
"STOCK & SALES ANALYSIS" as a clean column-aligned grid (one .xlsx per division:
COSMO, DERMA, COSMOQ, DERMACOR, COSMOCOR, PEDIA, PHARMA). Unlike the row-join
merged-column form that ``marg_sale_closing_xlsx`` (S.M. MEDICAL) handles, this
one keeps every value in its own fixed column, so we read it POSITIONALLY by
column index.

Two-row header::

    (row A)  '' | '' | <===SALE===> | '' | <==CLOSING==> | RE-
    (row B)  ITEM DESCRIPTION | QTY. | VALUE | QTY. | VALUE | ORDER | APR | MAR

so the 8 physical columns are::

    col0  ITEM DESCRIPTION   product text + trailing pack token  -> product_name (peel pack)
    col1  SALE  QTY.         -> sales_qty
    col2  SALE  VALUE        -> sales_value
    col3  CLOSING QTY.       -> closing_stock
    col4  CLOSING VALUE      -> closing_stock_value
    col5  RE-ORDER           (ignored — reorder suggestion, not a canonical field)
    col6  APR                (ignored — prior-month sale history)
    col7  MAR                (ignored — prior-month sale history)

The report genuinely carries NO opening / purchase / free / return columns, so
opening_stock and purchase_stock stay "0" and the sanity equation deliberately
cannot GREEN. The printed VALUE grand totals corroborate the extraction and the
value-corroborated / no_inflow_columns triage downgrade moves the file
RED->AMBER (never GREEN) — same disposition as S.M. MEDICAL.

Skipped rows:
  * the company/division band ('KLM-COSMO', 'KLM-DERMA', ...) — every cell holds
    the SAME band token, so the sale/closing cells are non-numeric -> skipped by
    the numeric-cell guard, but we also short-circuit it explicitly;
  * the per-report 'Total' footer (col0 == 'Total', SUBTOTAL_RE);
  * the 'MARG ERP NANO ...' advertising footer.
"""
import re

from extractors.stock_xlsx.constants import SUBTOTAL_RE
from extractors.stock_xlsx.parse_common import cell_text

_NUM_RE = re.compile(r"^-?\d+(?:\.\d+)?$")

# Fixed positional column map (0-based). Only these five columns carry canonical
# data; col5/col6/col7 (RE-ORDER / APR / MAR) are informational and dropped.
_SALE_QTY = 1
_SALE_VALUE = 2
_CLOSE_QTY = 3
_CLOSE_VALUE = 4

# The 'MARG ERP NANO for Chemist ...' advertising footer and the address banner
# repeat the SAME text across all 8 cells (an unmerged title row) — never a product.
_FOOTER_RE = re.compile(r"\bmarg\s+erp\b", re.I)


def _split_name_pack(text):
    """Peel the trailing pack token from the single col0 product string.

    col0 glues the pack as the LAST whitespace-separated token, e.g.
    'EKRAN 30 SILICON SU 30G' -> ('EKRAN 30 SILICON SU', '30G'),
    'HERPIVAL 1G TAB     3S'  -> ('HERPIVAL 1G TAB', '3S').
    """
    toks = text.split()
    if not toks:
        return "", ""
    if len(toks) == 1:
        return toks[0], ""
    return " ".join(toks[:-1]), toks[-1]


def parse_marg_sale_closing_grid_xlsx(rows):
    # Locate the header row: col0 text 'ITEM DESCRIPTION'.
    header_idx = None
    for idx in range(min(len(rows), 60)):
        first = cell_text(rows[idx][0]) if rows[idx] else ""
        if first.lower().replace(" ", "") == "itemdescription":
            header_idx = idx
            break
    if header_idx is None:
        return [], {}

    records = []
    for raw_row in rows[header_idx + 1:]:
        cells = [cell_text(c) for c in raw_row] if raw_row else []
        if not cells or not any(cells):
            continue

        name_cell = cells[0].strip()

        # Skip the company/division band ('KLM-COSMO' ...): the same token is
        # repeated across every cell, so the (would-be) sale/closing cells are
        # non-numeric. Detect by all-identical non-empty cells.
        non_empty = [c for c in cells if c.strip()]
        if len(non_empty) > 1 and len(set(non_empty)) == 1:
            continue

        low = name_cell.lower()
        # Skip the 'Total' footer (SUBTOTAL_RE anchored at start) and the
        # 'MARG ERP NANO ...' advertising footer.
        if name_cell and (SUBTOTAL_RE.match(name_cell) or _FOOTER_RE.search(low)):
            continue
        if low in {"itemdescription", "item description", "quantity", "value"}:
            continue

        # Require the SALE/CLOSING quantity + value columns to be numeric — this is
        # what separates a genuine product row from any residual band/label line.
        # This is also the sole gate for a data row whose ITEM DESCRIPTION cell is
        # blank (a product whose name failed to export, e.g. COSMOQ row 12): it
        # still carries the full numeric block and MUST be kept so the column sums
        # reconcile to the printed Total. product_name stays "" for that row.
        if len(cells) <= _CLOSE_VALUE:
            continue
        if not all(
            _NUM_RE.match(cells[i].strip())
            for i in (_SALE_QTY, _SALE_VALUE, _CLOSE_QTY, _CLOSE_VALUE)
        ):
            continue

        name, pack = _split_name_pack(name_cell)

        records.append(
            {
                "product_name": name,
                "pack": pack,
                "opening_stock": "0",
                "purchase_stock": "0",
                "sales_qty": cells[_SALE_QTY],
                "sales_value": cells[_SALE_VALUE],
                "closing_stock": cells[_CLOSE_QTY],
                "closing_stock_value": cells[_CLOSE_VALUE],
            }
        )

    detected = {
        "ITEM DESCRIPTION": "product_name",
        "PACK": "pack",
        "SALE QTY.": "sales_qty",
        "SALE VALUE": "sales_value",
        "CLOSING QTY.": "closing_stock",
        "CLOSING VALUE": "closing_stock_value",
    }
    return records, detected
