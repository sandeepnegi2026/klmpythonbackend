from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_numbers,
    _split_product_pack,
)


def parse_stock_simple_7col(text):
    """Simple Name/Pack/Open/Pur/Sales/Close: NAME PACK OPEN PURCHASE LASTPERIOD SALES SALEAMT CLOSING"""
    records = []
    for line in text.splitlines():
        s = line.strip()
        if _skip_line(s):
            continue
        prod, tail, _ = _split_product_numbers(s)
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
            "sales_qty": vals[3] if len(vals) >= 6 else vals[2],
            "sales_value": vals[4] if len(vals) >= 6 else 0.0,
            "closing_stock": vals[5] if len(vals) >= 6 else vals[-1],
        }
        records.append(r)
    return records
