import re

from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_numbers,
    _split_product_pack,
)


def parse_generic(text):
    """Fallback: try to extract any line with product name + at least 4 numbers."""
    records = []
    for line in text.splitlines():
        s = line.strip()
        if _skip_line(s):
            continue
        s2 = re.sub(r"^\d{1,3}\s+", "", s)
        prod, tail, exp = _split_product_numbers(s2 if s2 != s else s)
        if not prod or len(tail) < 4:
            continue
        name, pack = _split_product_pack(prod)
        vals = _nums(tail)
        if len(vals) < 4:
            continue
        r = {
            "product_name": name,
            "pack": pack,
            "opening_stock": vals[0],
            "purchase_stock": vals[1],
            "sales_qty": vals[2],
            "closing_stock": vals[-1],
        }
        if exp:
            r["expiry"] = exp
        records.append(r)
    return records
