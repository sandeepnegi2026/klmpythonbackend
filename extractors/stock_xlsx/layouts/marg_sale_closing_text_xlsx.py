"""Marg "STOCK & SALES ANALYSIS" reduced SALE/CLOSING report — single-column TEXT dump.

The text-dump twin of ``marg_sale_closing_xlsx`` (merged-grid) and
``marg_sale_closing_grid_xlsx`` (clean positional grid). SAM MEDICOS (KLM_S_S.XL.XLS)
exports the SAME reduced report — only two numeric groups, SALE and CLOSING, each a
(QTY, VALUE) pair, with NO opening/purchase/free/return columns — as fixed-width plain
text pasted into a SINGLE nbsp-padded cell of column A. Every data line is::

    <product ... pack>   SALE-QTY   SALE-VALUE   CLOSING-QTY   CLOSING-VALUE

The banner reads "<===SALE===>   <==CLOSING==>" over
"ITEM DESCRIPTION | QTY. | VALUE | QTY. | VALUE".

Because the whole line is one cell, the cell-splitting positional/merged parsers see
no trailing numeric CELLS and drop every row (UNKNOWN_LAYOUT / 0 rows). We instead join
the row, split on whitespace, and peel the trailing FOUR numbers, folding any surplus
leading numerics back into the product name (e.g. "KLM C 1000" keeps 1000 in the name).

Canonical mapping (report genuinely has NO opening/purchase, so those stay 0; the
value-corroborated / no_inflow_columns triage downgrade moves the file RED->AMBER,
never GREEN — identical disposition to the two sibling grid parsers)::

    sales_qty            = v[0]   (SALE  QTY.)
    sales_value          = v[1]   (SALE  VALUE)
    closing_stock        = v[2]   (CLOSING QTY.)
    closing_stock_value  = v[3]   (CLOSING VALUE)
    opening_stock = purchase_stock = 0

Negative closings/sales occur (e.g. DESOSOFT -> 20/1406 / -20/-1929) and are preserved.
Skipped: dash rules, the "SAM MEDICOS"/"STOCK & SALES ANALYSIS"/phone banners, the
"<===SALE===>" arrow banner, the "ITEM DESCRIPTION ... QTY. VALUE" label row, the
"Continued ..N" page markers, and the per-page "TOTAL <4 numbers>" footer.
"""
import re

from extractors.stock_xlsx.constants import SUBTOTAL_RE
from extractors.stock_xlsx.parse_common import cell_text

_NUM_RE = re.compile(r"^-?\d+(?:\.\d+)?$")
_NCOLS = 4

# The report appends a "PURCHASE DETAIL :-" supplier/purchase register after the last
# product page (SUPPLIER NAME | INVOICE NO. | DATE | ... | AMOUNT). Those lines can carry
# a trailing numeric block and must never be read as products. Same guard as the
# marg_sale_closing_xlsx sibling.
_BAND_RE = re.compile(
    r"\b(purchase\s+detail|supplier\s+name|invoice\s+no|receive\s+date|page\s+no)\b",
    re.I,
)


def parse_marg_sale_closing_text_xlsx(rows):
    records = []
    for row in rows:
        text = " ".join(cell_text(c) for c in row).replace("\xa0", " ") if row else ""
        stripped = text.strip()
        if not stripped or set(stripped) <= set("-= "):
            continue
        low = stripped.lower()

        # Banners / page markers / label rows carry no trailing 4-number block, so most
        # fall out below; skip the noisy ones explicitly to be safe.
        if low.startswith("continued") or low.startswith("stock & sales") \
                or low.startswith("sam medicos") or low.startswith("phone") \
                or low.startswith("e-mail"):
            continue
        if "item description" in low or "===sale===" in low.replace(" ", ""):
            continue
        if _BAND_RE.search(stripped):
            continue

        toks = stripped.split()
        nums = []
        while toks and _NUM_RE.match(toks[-1]):
            nums.append(toks.pop())
        nums.reverse()
        if len(nums) < _NCOLS:
            continue  # band / section title / partial line

        data = nums[-_NCOLS:]
        # Surplus leading numerics belong to the product name (e.g. "KLM C 1000").
        name = " ".join(toks + nums[:-_NCOLS]).strip()
        if not name:
            continue
        # Skip the per-page/grand "TOTAL <4 numbers>" footer and stray label words.
        if SUBTOTAL_RE.match(name) or name.strip().lower() in {
            "quantity",
            "value",
            "itemdescription",
            "item description",
        }:
            continue

        records.append(
            {
                "product_name": name,
                "opening_stock": "0",
                "purchase_stock": "0",
                "sales_qty": data[0],
                "sales_value": data[1],
                "closing_stock": data[2],
                "closing_stock_value": data[3],
            }
        )

    detected = {
        "ITEM DESCRIPTION": "product_name",
        "SALE QTY.": "sales_qty",
        "SALE VALUE": "sales_value",
        "CLOSING QTY.": "closing_stock",
        "CLOSING VALUE": "closing_stock_value",
    }
    return records, detected
