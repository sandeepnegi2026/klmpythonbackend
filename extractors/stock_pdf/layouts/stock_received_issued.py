from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_numbers,
    _split_product_pack,
)


def parse_stock_received_issued(text):
    """Stock & Sales with header 'Item Name Pack Opening Received Issued Closing [RplQty]'.

    vals[0]=opening, vals[1]=received (purchase), vals[2]=issued (sales),
    vals[3]=closing, vals[4]=RplQty (replacement qty, ignored).
    Reconciles: closing = opening + received - issued.
    """
    records = []
    for line in text.splitlines():
        s = line.strip()
        if _skip_line(s):
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
            "opening_stock": vals[0],
            "purchase_stock": vals[1],
            "sales_qty": vals[2],
            "closing_stock": vals[3],
        }
        if exp:
            r["expiry"] = exp
        records.append(r)
    return records
