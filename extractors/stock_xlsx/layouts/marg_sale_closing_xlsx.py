"""Marg "STOCK & SALES ANALYSIS" reduced SALE/CLOSING grid (xlsx twin).

Some KLM/Marg stockists export a *reduced* "STOCK & SALES ANALYSIS" that prints only two
numeric groups — SALE and CLOSING — each as a (QTY, VALUE) pair, with NO opening / purchase /
free / return columns at all. The banner row reads::

    <===SALE===>   <==CLOSING==>
    ITEM DESCRIPTION | QTY. | VALUE | QTY. | VALUE

Every product line therefore carries exactly FOUR trailing numbers::

    <product ... pack>   SALE-QTY   SALE-VALUE   CLOSING-QTY   CLOSING-VALUE

The xlsx twin is a grid where the product text is duplicated across ~5 merged columns
(unmerge fills every spanned cell), the pack sits in the next cell, and the four numbers land
in the trailing cells. We join each row, collapse the repeated product text, then read the
trailing-4-number block with the fixed SALE/CLOSING mapping.

Canonical mapping (this report genuinely has NO opening/purchase, so those stay 0 and the
sanity equation deliberately cannot GREEN — the printed VALUE grand totals corroborate the
extraction and the value-corroborated downgrade moves the file RED->AMBER, never GREEN)::

    sales_qty            = v[0]   (SALE  QTY.)
    sales_value          = v[1]   (SALE  VALUE)
    closing_stock        = v[2]   (CLOSING QTY.)
    closing_stock_value  = v[3]   (CLOSING VALUE)
    opening_stock = purchase_stock = 0

Negative closings occur (e.g. IMXIA 5 -> -6 / -3415) and are preserved. Division/company
bands ("KLM COSMOQ", "KLM LABORATORIES PVT.LTD(COSMO"), per-group "Total ..." lines, the
"Continued .." page markers and the appended supplier/purchase register ("SUPPLIER NAME
INVOICE NO. ...") are all skipped.
"""
import re

from extractors.stock_xlsx.constants import SUBTOTAL_RE
from extractors.stock_xlsx.parse_common import cell_text

_NUM_RE = re.compile(r"^-?\d+(?:\.\d+)?$")
_NCOLS = 4

# Rows that mark the appended purchase/supplier register or a page marker — never products.
# NB: division/company bands ("KLM COSMOQ", "KLM LABORATORIES PVT.LTD(...)") carry NO trailing
# 4-number block, so they are excluded by the numeric-tail requirement below — we must NOT gate
# on "KLM" here, or genuine KLM-branded products (KLM D3, KLM KLIN, KLM C 20...) would be lost.
_BAND_RE = re.compile(
    r"\b(purchase\s+detail|supplier\s+name|invoice\s+no|receive\s+date|page\s+no)\b",
    re.I,
)


def _dedupe_consecutive(cells):
    """Collapse the repeated (unmerged) product text: drop empties and consecutive dupes."""
    out = []
    for c in cells:
        c = c.strip()
        if not c:
            continue
        if out and out[-1] == c:
            continue
        out.append(c)
    return out


def _split_name_pack(cells):
    """From the leading (non-numeric) cells, take the LAST token as pack, the rest as name."""
    toks = _dedupe_consecutive(cells)
    if not toks:
        return "", ""
    if len(toks) == 1:
        return toks[0], ""
    pack = toks[-1]
    name = " ".join(toks[:-1])
    return name, pack


def parse_marg_sale_closing_xlsx(rows):
    records = []
    for row in rows:
        cells = [cell_text(c) for c in row] if row else []
        joined = " ".join(c for c in cells if c).strip()
        if not joined or set(joined) <= set("-= "):
            continue
        low = joined.lower()

        # The banner ("<===SALE===>") and the "ITEM DESCRIPTION | QTY. | VALUE ..." label row
        # carry no trailing numeric block, so they fall out naturally below; but skip the
        # page markers / division bands / appended supplier register explicitly.
        if low.startswith("continued") or "page no" in low:
            continue
        if _BAND_RE.search(joined):
            continue

        # Split off the trailing numeric block. We require EXACTLY four trailing numbers
        # (SALE qty/value, CLOSING qty/value). Fewer -> a band/section title; more -> the
        # extra leading numerics are product-name tokens (e.g. "IMXIA 5"), so keep only the
        # last four as data and fold the rest back into the name.
        nums = []
        idx = len(cells)
        while idx > 0 and _NUM_RE.match(cells[idx - 1].strip()):
            nums.append(cells[idx - 1].strip())
            idx -= 1
        nums.reverse()
        if len(nums) < _NCOLS:
            continue  # band / total / partial line

        data = nums[-_NCOLS:]
        lead = cells[:idx] + nums[:-_NCOLS]  # any surplus numbers belong to the name
        name, pack = _split_name_pack(lead)
        if not name:
            continue
        # Skip subtotal footers: SUBTOTAL_RE is anchored at the START ("Total ...", the
        # all-caps cumulative "TOTAL ...", "grand total", "value in rs" ...), so a genuine
        # product whose name merely ENDS in "TOTAL" (e.g. "EXTEND TOTAL", pack 15S) is kept.
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
                "pack": pack,
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
        "PACK": "pack",
        "SALE QTY.": "sales_qty",
        "SALE VALUE": "sales_value",
        "CLOSING QTY.": "closing_stock",
        "CLOSING VALUE": "closing_stock_value",
    }
    return records, detected
