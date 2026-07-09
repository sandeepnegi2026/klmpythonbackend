from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_numbers,
    _split_product_pack,
)


def parse_stock_open_pur_sale_amt(text):
    """KLM stock register (Rohtak/Friends style).

    Columns: ITEM  OPENING  PURCHASE  SALE  AMOUNT-I  CL.STOCK  AMOUNT-II
             [NEAR EXP.  N.E.VALUE]
    closing = CL.STOCK (vals[4]); vals[3]/vals[5] are rupee amounts.
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
            "sales_qty": vals[2],
            "sales_value": vals[3],
            "closing_stock": vals[4],
            "closing_stock_value": vals[5] if len(vals) > 5 else 0.0,
        }
        if exp:
            r["expiry"] = exp
        records.append(r)
    return records
