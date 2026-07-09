import re

from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_numbers,
    _split_product_pack,
)


def parse_marg_lms_simple(text):
    """Marg LMS Simple: PRODUCT OPENING PURCHASE LMS SALES CLOSING [NEAREXP]"""
    records = []
    division = ""
    for line in text.splitlines():
        s = line.strip()
        if _skip_line(s):
            continue
        if s.startswith("SALES AMOUNT") or s.startswith("STOCK VALUE"):
            continue
        if re.match(r"^KLM\s", s, re.I):
            division = s
            continue
        if s.startswith("PRODUCT ") and "OPENING" in s:
            continue
        if re.match(r"^(TIRUPATI|RAJNANDGAON|AHUJA|DAD|NITIN|\d{2}/\d{2}/)", s):
            continue
        prod, tail, exp = _split_product_numbers(s)
        if not prod or len(tail) < 4:
            continue
        name, pack = _split_product_pack(prod)
        vals = _nums(tail)
        if len(vals) < 4:
            continue
        r = {
            "product_name": name,
            "pack": pack,
            "division": division,
            "opening_stock": vals[0],
            "purchase_stock": vals[1],
            "sales_qty": vals[3] if len(vals) >= 5 else vals[2],
            "closing_stock": vals[4] if len(vals) >= 5 else vals[3],
        }
        if exp:
            r["expiry"] = exp
        records.append(r)
    return records
