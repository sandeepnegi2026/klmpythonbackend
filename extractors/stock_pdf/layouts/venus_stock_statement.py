import re

from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_numbers,
    _split_product_pack,
)


def parse_venus_stock_statement(text):
    """Venus Stock Statement: Item_Name Pack Dec Jan Op. Pur SP Sale SS SVal Cr. Db. Adj. C_Stk C_Val Ord."""
    records = []
    division = ""
    for line in text.splitlines():
        s = line.strip()
        if _skip_line(s):
            continue
        if re.match(r"^KLM\s+LAB", s, re.I):
            division = re.sub(r"\s+X[A-Z]\d+$", "", s).strip()
            continue
        if re.match(
            r"^(Opening Value|Closing Value|Sales\s*:|Report Date|VENUS|Sales Value|Credit|Debit|MG\d)",
            s,
        ):
            continue
        if (
            "Purchase Value" in s
            or s.startswith("37,")
            or s.startswith("Stock and Sales")
        ):
            continue
        if s.startswith("Item Name"):
            continue
        prod, tail, _ = _split_product_numbers(s)
        if not prod or len(tail) < 2:
            continue
        name, pack = _split_product_pack(prod)
        vals = _nums(tail)
        if len(vals) < 2:
            continue
        r = {"product_name": name, "pack": pack, "division": division}
        n = len(vals)
        r["closing_stock_value"] = vals[-1]
        r["closing_stock"] = vals[-2] if n >= 2 else 0.0
        if n >= 12:
            r["opening_stock"] = vals[2]
            r["purchase_stock"] = vals[3]
            r["sales_qty"] = vals[5]
            r["sales_free"] = vals[6]
            r["sales_value"] = vals[7]
        elif n >= 6:
            r["opening_stock"] = vals[0]
            r["purchase_stock"] = vals[1]
            r["sales_qty"] = vals[-5] if n >= 7 else vals[2]
            r["sales_free"] = vals[-4] if n >= 7 else 0.0
            r["sales_value"] = vals[-3]
        elif n >= 5:
            r["opening_stock"] = vals[0]
            r["purchase_stock"] = vals[1]
            r["sales_qty"] = vals[-4] if n >= 6 else vals[2]
            r["sales_value"] = vals[-3] if n >= 6 else 0.0
        elif n >= 3:
            r["opening_stock"] = vals[0]
        records.append(r)
    return records
