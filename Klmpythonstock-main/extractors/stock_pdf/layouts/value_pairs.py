from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_numbers,
    _split_product_pack,
)


def parse_value_pairs(text):
    """Marg Qty-Value Pairs: product [RATE] OPEN_QTY OPEN_VAL RECEIPT_QTY RECEIPT_VAL ISSUE_QTY ISSUE_VAL CLOSE_QTY CLOSE_VAL [DUMP] [M.EXP]"""
    records = []
    for line in text.splitlines():
        s = line.strip()
        if _skip_line(s):
            continue
        prod, tail, exp = _split_product_numbers(s)
        if not prod or len(tail) < 8:
            continue
        name, pack = _split_product_pack(prod)
        vals = _nums(tail)
        if len(vals) < 8:
            continue
        offset = 0
        if len(vals) >= 9 and vals[0] > 0:
            offset = 1
        r = {
            "product_name": name,
            "pack": pack,
            "rate": vals[0] if offset else 0.0,
            "opening_stock": vals[offset],
            "opening_value": vals[offset + 1],
            "purchase_stock": vals[offset + 2],
            "purchase_value": vals[offset + 3],
            "sales_qty": vals[offset + 4],
            "sales_value": vals[offset + 5],
            "closing_stock": vals[offset + 6],
            "closing_stock_value": vals[offset + 7]
            if offset + 7 < len(vals)
            else 0.0,
        }
        if exp:
            r["expiry"] = exp
        records.append(r)
    return records
