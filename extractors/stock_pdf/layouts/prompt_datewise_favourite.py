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

--- PACK-FRAGMENT LEAK GUARD (additive, reconcile-gated) --------------------------
A tiny minority of rows carry a PACK whose unit label is missing from the text layer,
so a bare pack COUNT leaks into the numeric tail AHEAD of the six real value columns
(OpStk|Pur|Sales|ClStk|Amount|A3Mn). Examples (all genuine no-stock catalogue SKUs):
    'NS-6 OINT. 1 0 0 0 0 0 0'                 (DEV MEDICAL, ebb6.pdf)
    'EXTEND-HAIR GUMMY POCHES 30 0 0 0 0 0 0'  (MEDICARE, klm may-2026.pdf)
    'SOFIKID 1*30 GUMMY POCHES 1 0 0 0 0 0 0'  (MEDICARE, klm may-2026.pdf)
Here the leading number is a pack fragment, NOT the opening qty, so reading OpStk from
tail[0] injects a phantom opening (op=1/30) that BREAKS the reconcile identity
(op + pur - sales != clos) for an otherwise all-zero row.

The guard fires ONLY when the tail has SEVEN numbers (one more than the six real
columns) AND the standard window tail[0:4] FAILS the reconcile identity while the
one-position-shifted window tail[1:5] PASSES it. That double condition is
self-validating: it can only ever help a row the current mapping already mis-reconciles
and where the shift makes it reconcile — it cannot touch a row that already reconciles.
Rows with a legitimately populated Favourite column (e.g. VIVEK f345.pdf: 43 rows whose
seven-number tail is 'op pur sale clos amount a3mn favourite' with the first four
correctly left-aligned and already reconciling) are UNAFFECTED, because their tail[0:4]
already passes the identity so the guard never triggers.
"""
import re

from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_numbers,
    _split_product_pack,
)


def _reconciles(op, pur, sale, clos):
    """closing == opening + purchase - sales, within 5% of closing (or 1 unit)."""
    return abs((op + pur - sale) - clos) <= 0.05 * max(abs(clos), 1)


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

        # Standard mapping: the four leading numbers are the qty columns and the
        # fifth is the closing-stock rupee value ('Amount').
        base = 0
        # Pack-fragment leak guard (see module docstring): when a bare pack count
        # leaks in front of the six real columns the tail holds SEVEN numbers and
        # the standard window mis-reconciles while the shifted window reconciles.
        if (
            len(vals) == 7
            and not _reconciles(vals[0], vals[1], vals[2], vals[3])
            and _reconciles(vals[1], vals[2], vals[3], vals[4])
        ):
            base = 1  # skip the leaked leading pack fragment

        op, pur, sale, clos = (
            vals[base], vals[base + 1], vals[base + 2], vals[base + 3]
        )

        r = {
            "product_name": name,
            "pack": pack,
            "opening_stock": op,
            "purchase_stock": pur,
            "sales_qty": sale,
            "closing_stock": clos,
        }
        if len(vals) >= base + 5:
            r["closing_stock_value"] = vals[base + 4]  # 'Amount' = closing stock value
        if exp:
            r["expiry"] = exp
        records.append(r)
    return records
