from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_numbers_comma as _split_product_numbers,
    _split_product_pack,
)


def parse_marg_stock_long(text):
    """Marg Long Stock Movements: product OPENING SALE REPL_PUR RETURN_OTHERS TOTAL PURCHASE REPL_SAL RETURN_OTHERS CLOSING RATE [M.EXP]"""
    records = []
    for line in text.splitlines():
        s = line.strip()
        if _skip_line(s):
            continue
        prod, tail, exp = _split_product_numbers(s)
        if not prod or len(tail) < 9:
            continue
        name, pack = _split_product_pack(prod)
        vals = _nums(tail)
        if len(vals) < 9:
            continue
        r = {
            "product_name": name,
            "pack": pack,
            "opening_stock": vals[0],
            "sales_qty": vals[1],
            "purchase_return": vals[2],
            "purchase_stock": vals[5] if len(vals) > 5 else 0.0,
            "sales_return": vals[6] if len(vals) > 6 else 0.0,
            "closing_stock": vals[8] if len(vals) > 8 else vals[-2],
            "rate": vals[9] if len(vals) > 9 else 0.0,
        }
        if exp:
            r["expiry"] = exp
        records.append(r)
    return records
