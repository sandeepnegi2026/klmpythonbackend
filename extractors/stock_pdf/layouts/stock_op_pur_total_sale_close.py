from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_numbers,
    _split_product_pack,
)


def parse_stock_op_pur_total_sale_close(text):
    """Stock statement with an explicit TOTAL column between purchase and sales.

    Header variants (same column order):
      Sr. Product Name Pack  Op.Stk  Pr/Rec  Total  Sl/Iss  Cl.Stk  [Rate MRP Exp] Cl.Val
      Product Name Pack       Op Bal  Pur    Total  Sales   Cl Bal  [CP]

    vals[0]=opening, vals[1]=purchase/receipt, vals[2]=TOTAL (=op+pur, ignored),
    vals[3]=sales/issue, vals[4]=closing; trailing numbers are rate/mrp/value.
    Reconciles: closing = opening + purchase - sales.
    """
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
