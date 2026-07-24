import re

from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_numbers,
    _split_product_pack,
)


def parse_dahod_marg(text):
    """Marg Item-Code Register: ItemCd ItemName Packing OpStk PQty PSQty PVal SQty SSQty SSp SQty SVal CQty CSQty DQty AQty ClStk ClVal"""
    records = []
    for line in text.splitlines():
        s = line.strip()
        if _skip_line(s):
            continue
        m = re.match(r"^([A-Z0-9]{4,8})\s+(.+?)(\s+\d|$)", s)
        if not m or not any(c.isdigit() for c in m.group(1)):
            continue
        rest = m.group(2).strip() + m.group(3) + s[m.end(3) :]
        prod, tail, _ = _split_product_numbers(rest)
        if not prod:
            prod = rest
            tail = []
        name, pack = _split_product_pack(prod)
        vals = _nums(tail)
        name_upper = name.upper()
        if "DIVISION" in name_upper or "DIVISON" in name_upper or name_upper.endswith(" DIVI"):
            continue
        if m.group(1).startswith("D00") and len(vals) == 0:
            continue
        r = {"product_name": name, "pack": pack, "product_code": m.group(1)}
        if len(vals) > 0:
            if len(vals) == 1:
                r["closing_stock"] = vals[0]
                r["opening_stock"] = vals[0]
            else:
                r["opening_stock"] = vals[0]
                r["closing_stock"] = vals[-2]
                r["closing_stock_value"] = vals[-1]
                if len(vals) >= 6:
                    r["purchase_stock"] = vals[1]
                    r["sales_qty"] = vals[3] if len(vals) >= 7 else vals[2]
        else:
            r["opening_stock"] = 0.0
            r["closing_stock"] = 0.0
        records.append(r)
    return records
