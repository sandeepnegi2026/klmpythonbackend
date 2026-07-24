import re

from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_numbers,
    _split_product_pack,
)

# --- KLM/VIVEK Rate-MRP-ClVal pack-leak repair -----------------------------
# A bare pack-size integer that trails a dosage-form word with NO unit letter
# ("MELBOOST NXT TAB 10", "ONITRAZ CAP 10") is peeled into the number run by
# _split_product_numbers because it is a pure integer. In the KLM/VIVEK export
# the header carries a 'Rate  M.R.P.  Exp  Cl.Val' block; those Rate/MRP DECIMAL
# tokens make the five stat columns (Op.Stk Pr/Rec Total Sl/Iss Cl.Stk) exactly
# the integers that sit immediately BEFORE the first decimal. When the bare pack
# leaks there are SIX such integers, so opening steals the pack and every stat
# column shifts right by one (reconcile breaks). The 'Total' cross-check column
# confirms the shift: for the correct mapping vals[0]+vals[1]==vals[2]; a leaked
# row instead satisfies vals[1]+vals[2]==vals[3].
#
# Gated to the Rate/MRP header ('m.r.p' token) which — across the whole 15-July
# corpus for this layout — appears ONLY in this VIVEK variant. The value-less
# SHREENATH sibling (Op.Stk..Cl.Stk Cl.Val, no Rate/MRP) and the 'Op Bal'/'
# OPENING PURCHASE' Metro/New-Singh/City families do NOT carry 'm.r.p', so they
# take the untouched original path.
_DECIMAL_RE = re.compile(r"^\d[\d,]*\.\d+$")
_INT_RE = re.compile(r"^\d+$")


def _has_mrp_header(text):
    low = text.lower()
    return "m.r.p" in low and "op.stk" in low and "cl.stk" in low


def _leading_int_run_before_decimal(tail):
    """Length of the pure-integer run at the head of ``tail`` up to the first
    decimal (Rate) token. Returns (run_len, decimal_seen)."""
    run = 0
    for t in tail:
        if _DECIMAL_RE.match(t):
            return run, True
        if _INT_RE.match(t.replace(",", "")):
            run += 1
            continue
        return run, False
    return run, False


def parse_stock_op_pur_total_sale_close(text):
    """Stock statement with an explicit TOTAL column between purchase and sales.

    Header variants (same column order):
      Sr. Product Name Pack  Op.Stk  Pr/Rec  Total  Sl/Iss  Cl.Stk  [Rate MRP Exp] Cl.Val
      Product Name Pack       Op Bal  Pur    Total  Sales   Cl Bal  [CP]

    vals[0]=opening, vals[1]=purchase/receipt, vals[2]=TOTAL (=op+pur, ignored),
    vals[3]=sales/issue, vals[4]=closing; trailing numbers are rate/mrp/value.
    Reconciles: closing = opening + purchase - sales.
    """
    mrp_variant = _has_mrp_header(text)
    records = []
    for line in text.splitlines():
        s = line.strip()
        if _skip_line(s):
            continue
        prod, tail, exp = _split_product_numbers(s)
        if not prod or len(tail) < 5:
            continue
        name, pack = _split_product_pack(prod)
        vals = _nums(tail)
        if len(vals) < 5:
            continue

        # Pack-leak repair (KLM/VIVEK Rate/MRP variant only). Fire only when the
        # bare pack sits in the stat run (six integers before the Rate decimal)
        # AND the Total cross-check proves the shift (op+pur != total on the raw
        # mapping, but pur+total == sale on the shifted mapping). Drop the leaked
        # pack; adopt it as pack only if the layout's own pack column was empty.
        if mrp_variant and len(vals) >= 6:
            run, decimal_seen = _leading_int_run_before_decimal(tail)
            if (
                decimal_seen
                and run == 6
                and abs(vals[0] + vals[1] - vals[2]) > 0.5
                and abs(vals[1] + vals[2] - vals[3]) <= 0.5
            ):
                leaked = tail[0]
                vals = vals[1:]
                if not pack:
                    pack = leaked

        r = {
            "product_name": name,
            "pack": pack,
            "opening_stock": vals[0],
            "purchase_stock": vals[1],
            "sales_qty": vals[3],
            "closing_stock": vals[4],
        }
        if exp:
            r["expiry"] = exp
        records.append(r)
    return records
