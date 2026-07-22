import re

from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_numbers_comma as _split_product_numbers,
    _split_product_pack,
)

# Leading "Sn." serial column (e.g. "12 COSMOQ ...") — always an integer followed
# by the product text. Strip it so it doesn't pollute the product name.
_SERIAL_RE = re.compile(r"^\d+\s+(?=\D)")


def parse_marg_stock_summary(text):
    """Marg 'STOCK SUMMARY' — 8 qty/value movement groups in a fixed order:

        Opening | Purchases | Pur. Returns | Receipts | Sales | Sales Return | Issue | Balance

    Each group is a (Qty, Value) pair EXCEPT Balance, which carries (Qty, Rate,
    Value), and every row ends with a GST %. So after the leading Sn. serial each
    data line has 7*(Qty Value) + Balance(Qty Rate Value) + GST = 18 numbers.

    Receipts and Issue are the non-purchase inflow / non-sale outflow columns
    (branch transfers, samples). They map to purchase_free / sales_free so the
    reconciliation equation stays exact when they are non-zero:
        Balance = Opening + Purchases + Receipts - Pur.Returns - Sales - Issue + Sales Return
    """
    records = []
    for line in text.splitlines():
        s = line.strip()
        if _skip_line(s):
            continue
        prod, tail, exp = _split_product_numbers(s)
        if not prod:
            continue
        vals = _nums(tail)
        if len(vals) < 18:
            continue
        vals = vals[-18:]  # ignore any stray leading number captured in the tail
        prod = _SERIAL_RE.sub("", prod).strip()
        name, pack = _split_product_pack(prod)
        r = {
            "product_name": name,
            "pack": pack,
            "opening_stock": vals[0],
            "opening_value": vals[1],
            "purchase_stock": vals[2],
            "purchase_value": vals[3],
            "purchase_return": vals[4],
            # vals[5] = Pur. Returns value (no canonical field)
            "purchase_free": vals[6],   # Receipts qty (inflow)
            # vals[7] = Receipts value
            "sales_qty": vals[8],
            "sales_value": vals[9],
            "sales_return": vals[10],
            "sales_return_value": vals[11],
            "sales_free": vals[12],     # Issue qty (outflow)
            # vals[13] = Issue value
            "closing_stock": vals[14],
            "rate": vals[15],           # Balance rate
            "closing_stock_value": vals[16],
            "gst_rate": vals[17],
        }
        if exp:
            r["expiry"] = exp
        records.append(r)
    return records
