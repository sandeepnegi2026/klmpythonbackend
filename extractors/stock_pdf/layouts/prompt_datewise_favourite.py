"""Prompt ERP 'Stock Statement (Datewise)' — 4 pure-qty variant (DEV MEDICAL AGENCY).

Header:  Product Name | Pack | OpStk | Pur | Sales | ClStk | A3Mn | Favourite
Sub:                            Qty    Qty   Qty     Qty     Amount

Each row's numeric tail is:  OpStk, Pur, Sales, ClStk(Qty), Amount, A3Mn
  * OpStk / Pur / Sales / ClStk are pure quantities (the division `Total:` lines carry
    exactly these four and reconcile ClStk = OpStk + Pur - Sales).
  * Amount is the closing-stock rupee VALUE (sub-header 'Amount', ~closing_qty x rate).
  * A3Mn is the 3-MONTH AVERAGE quantity — an informational stat, NOT closing stock.
  * Favourite is a trailing flag column, empty in the data body.

This differs from the base `prompt` layout (which expects OpStk/Pur/Sales/Free/Inst/
ClStk/Amount and reads closing from tail index 5). Here index 5 is A3Mn, so the base
parser puts the 3-month average into closing_stock -> ~98% false SANITY_FAILED. We map
closing from index 3 and the value from index 4. Gated on the unique 'Favourite'
column, which no other Prompt export carries.
"""
import re

from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_numbers,
    _split_product_pack,
)


def parse_prompt_datewise_favourite(text):
    records = []
    for line in text.splitlines():
        s = line.strip()
        if _skip_line(s):
            continue
        # data rows start with a serial index; band/total/footer lines do not
        if not re.match(r"^\d+\s", s):
            continue
        s = re.sub(r"^\d+\s+", "", s)

        prod, tail, exp = _split_product_numbers(s)
        if not prod:
            continue
        vals = _nums(tail)
        if len(vals) < 4:  # need at least the 4 qty columns
            continue

        name, pack = _split_product_pack(prod)
        op, pur, sale, clos = vals[0], vals[1], vals[2], vals[3]

        # KEEP zero-stock rows: this Prompt report deliberately lists every catalog SKU
        # (0 opening / 0 movement / 0 closing is a genuine no-stock product, not an
        # extraction artifact), so dropping them loses real inventory records. Triage's
        # effective_sanity already excludes all-zero rows from the reconciliation, so
        # retaining them cannot create a false SANITY signal.

        r = {
            "product_name": name,
            "pack": pack,
            "opening_stock": op,
            "purchase_stock": pur,
            "sales_qty": sale,
            "closing_stock": clos,
        }
        if len(vals) >= 5:
            r["closing_stock_value"] = vals[4]  # 'Amount' = closing stock value
        if exp:
            r["expiry"] = exp
        records.append(r)
    return records
