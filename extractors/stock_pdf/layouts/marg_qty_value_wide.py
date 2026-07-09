from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_numbers,
    _split_product_pack,
)


def parse_marg_qty_value_wide(text):
    """Marg Qty-Value Wide: product QTY VALUE pairs for opening, purchase, sales, closing [M.EXP]"""
    records = []
    # Marg 21-col "STOCK & SALES ANALYSIS" carries a PURCHASE RETURN QTY group at
    # tail index 16; only map it when the page header explicitly names that group.
    has_purchase_return = "purchase return" in text.lower()
    for line in text.splitlines():
        s = line.strip()
        if _skip_line(s):
            continue
        prod, tail, exp = _split_product_numbers(s)
        if not prod or len(tail) < 15:
            continue
        name, pack = _split_product_pack(prod)
        vals = _nums(tail)
        if len(vals) == 22 and not pack:
            pack = str(int(vals[0])) if vals[0].is_integer() else str(vals[0])
            vals = vals[1:]
        if len(vals) < 15:
            continue
        r = {
            "product_name": name,
            "pack": pack,
            "opening_stock": vals[0],
            "opening_value": vals[1],
            "purchase_stock": vals[2],
            "purchase_free": vals[3],
            "purchase_value": vals[4],
            "sales_return": vals[5],
            "sales_qty": vals[10] if len(vals) > 10 else vals[-4],
            "sales_free": vals[11] if len(vals) > 11 else 0.0,
            "sales_value": vals[12] if len(vals) > 12 else 0.0,
            "closing_stock": vals[-2] if len(vals) > 4 else vals[-1],
            "closing_stock_value": vals[-1],
        }
        if has_purchase_return and len(vals) >= 21:
            r["purchase_return"] = vals[16]
        if exp:
            r["expiry"] = exp
        records.append(r)
    return records
