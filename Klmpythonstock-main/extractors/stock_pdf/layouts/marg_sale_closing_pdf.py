"""Marg "STOCK & SALES ANALYSIS" reduced SALE/CLOSING report (S.M. MEDICAL ENTERPRISE).

This is the *reduced* Marg analysis export that prints ONLY the sale and closing
qty/value pairs — opening, purchase and free columns are dropped by the vendor:

    STOCK & SALES ANALYSIS 01/06/2026 - 23/06/2026
    <===SALE===>   <==CLOSING==>
    ITEM DESCRIPTION   QTY.  VALUE   QTY.  VALUE

Each product line is `<product> <pack> <SALE_QTY> <SALE_VALUE> <CLOSING_QTY>
<CLOSING_VALUE>` — exactly four trailing numbers. We map:

    sales_qty           = v[-4]
    sales_value         = v[-3]
    closing_stock       = v[-2]   (QTY, not the rupee value)
    closing_stock_value = v[-1]

opening_stock / purchase_stock are genuinely absent -> 0 (so full open+pur-sale
reconciliation cannot hold; the value-corroborated sanity downgrade lifts RED->AMBER
using the printed VALUE grand totals, never GREEN).

Skipped:
  * division/company bands ("KLM COSMOQ", "KLM LABORATORIES PVT.LTD(COSMO", ...)
  * per-group / grand "Total"/"TOTAL <..>" lines (SUBTOTAL_RE)
  * the appended supplier/purchase register at the tail
    ("PURCHASE DETAIL", "SUPPLIER NAME INVOICE NO. ...", date-bearing supplier rows)

The text layer is flat and well-aligned for this export, so a line parser (last-4
numbers) suffices — no positional x-binning is required here. Negative closings
(e.g. IMXIA 5: -6 / -3415) are kept.
"""
import re

from extractors.stock_pdf.constants import SKIP_RE, SUBTOTAL_RE
from extractors.stock_pdf.parse_common import (
    _nums,
    _split_product_numbers,
    _split_product_pack,
)

# The appended supplier/purchase register at the tail. Once we cross into it we
# must ignore every following line (supplier rows carry 5 tail numbers too).
_PURCHASE_HEADER_RE = re.compile(
    r"purchase detail|supplier name|invoice no", re.I
)


def _skip(s):
    """Local skip that (unlike parse_common._skip_line) does NOT drop lines that
    merely start with 'KLM ' — this vendor sells genuine products named KLM D3 /
    KLM FX / KLM KLIN / KLM AHA / KLM C 20, which the shared helper would eat.
    Division/company band headings ("KLM COSMOQ", "KLM LABORATORIES PVT.LTD(COSMO")
    carry NO trailing numbers, so the 4-number requirement in the caller drops them
    instead. Here we only reject genuinely empty/short lines, separators and the
    Total / column-header / section-title rows."""
    if not s or len(s) < 5:
        return True
    if SUBTOTAL_RE.match(s) or SKIP_RE.match(s):
        return True
    if re.match(r"^[\d\s\-]+$", s):  # pure separator / rule line
        return True
    return False


def parse_marg_sale_closing_pdf(text):
    records = []
    in_purchase_register = False

    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue

        # Once the supplier/purchase register begins, drop the rest of the file.
        if _PURCHASE_HEADER_RE.search(s):
            in_purchase_register = True
            continue
        if in_purchase_register:
            continue

        if _skip(s):
            continue

        prod, tail, _exp = _split_product_numbers(s)
        if not prod:
            continue

        vals = _nums(tail)
        if len(vals) < 4:
            # division/company band heading (no trailing numbers) or a stray line
            continue

        # NOTE: per-group / grand "Total <..>" summary lines start with the word
        # "total" and are already removed by SUBTOTAL_RE inside _skip(); we must NOT
        # also reject product text merely *containing* "total" or the vendor's real
        # product "EXTEND TOTAL 15S" (closing 14/1410) would be lost.

        v = vals[-4:]  # exactly the four SALE/CLOSING columns (ignore code digits
                       # that may have been peeled off the product name/pack)
        name, pack = _split_product_pack(prod)

        # Guard against total/band rows that somehow carried 4 numbers.
        if not name.strip():
            continue

        sale_qty, sale_value, close_qty, close_value = v[0], v[1], v[2], v[3]

        records.append({
            "product_name": name,
            "pack": pack,
            "opening_stock": 0.0,
            "purchase_stock": 0.0,
            "sales_qty": sale_qty,
            "sales_value": sale_value,
            "closing_stock": close_qty,
            "closing_stock_value": close_value,
        })

    return records
