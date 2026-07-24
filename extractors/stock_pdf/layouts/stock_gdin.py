from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_numbers_comma as _split_product_numbers,
    _split_product_pack,
)


def parse_stock_gdin(text):
    """KLM 'Stock and Sale' with goods-in / goods-out columns (Senior style).

    Columns: PRODUCT PACK  Op  Pur  Gd.In  TotIn  Sale  Gd.Out  Closing
             [PurValue  SaleValue  StockValue]
    Reconciles as opening + pur + Gd.In - Sale - Gd.Out = Closing, so Gd.In is
    mapped to sales_return (adds back) and Gd.Out to purchase_return (subtracts).
    """
    records = []
    for line in text.splitlines():
        s = line.strip()
        if _skip_line(s):
            continue
        prod, tail, exp = _split_product_numbers(s)
        if not prod or len(tail) < 7:
            continue
        name, pack = _split_product_pack(prod)
        vals = _nums(tail)
        if len(vals) < 7:
            continue
        r = {
            "product_name": name,
            "pack": pack,
            "opening_stock": vals[0],
            "purchase_stock": vals[1],
            "sales_return": vals[2],     # Gd.In (goods received back)
            "sales_qty": vals[4],
            "purchase_return": vals[5],  # Gd.Out (goods returned out)
            "closing_stock": vals[6],
        }
        if exp:
            r["expiry"] = exp
        records.append(r)
    return records
