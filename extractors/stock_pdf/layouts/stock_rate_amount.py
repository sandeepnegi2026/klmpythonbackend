from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_numbers,
    _split_product_pack,
)


def parse_stock_rate_amount(text):
    """Rate + Amount Columns: PRODUCT RATE OPEN PUR LPS SALES AMOUNT CLOSE AMOUNT NEAREXP"""
    records = []
    for line in text.splitlines():
        s = line.strip()
        if _skip_line(s):
            continue
        prod, tail, exp = _split_product_numbers(s)
        if not prod or len(tail) < 6:
            continue
        name, pack = _split_product_pack(prod)
        vals = _nums(tail)
        if len(vals) < 6:
            continue
        r = {
            "product_name": name,
            "pack": pack,
            "rate": vals[0],
            "opening_stock": vals[1],
            "purchase_stock": vals[2],
            "sales_qty": vals[4] if len(vals) >= 7 else vals[3],
            "sales_value": vals[5] if len(vals) >= 7 else vals[4],
            "closing_stock": vals[6]
            if len(vals) >= 8
            else vals[5]
            if len(vals) >= 6
            else vals[-1],
            "closing_stock_value": vals[7] if len(vals) >= 8 else 0.0,
        }
        if exp:
            r["expiry"] = exp
        records.append(r)
    return records
