from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_numbers,
    _split_product_pack,
)


def parse_stock_receipt_replace(text):
    """Receipt/Replace Statement: Product Opening Receipt ReceiptFree Total Sale Free"""
    records = []
    for line in text.splitlines():
        s = line.strip()
        if _skip_line(s):
            continue
        prod, tail, _ = _split_product_numbers(s)
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
        }
        if len(vals) >= 7:
            r["purchase_free"] = vals[2]
            total = vals[4] if len(vals) >= 5 else vals[0] + vals[1] + vals[2]
            r["sales_qty"] = vals[5] if len(vals) >= 6 else 0.0
            r["sales_free"] = vals[6] if len(vals) >= 7 else 0.0
            r["closing_stock"] = total - r["sales_qty"] - r["sales_free"]
        elif len(vals) >= 4:
            r["sales_qty"] = vals[2]
            r["closing_stock"] = vals[3]
        records.append(r)
    return records
