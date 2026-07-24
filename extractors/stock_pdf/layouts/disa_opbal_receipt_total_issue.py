from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_numbers_comma as _split_product_numbers,
    _split_product_pack,
)


def parse_disa_opbal_receipt_total_issue(text):
    """DISA ERP Stock & Sales Statement.

    Header: PRODUCT NAME  Shelf-ID  Tax-Rate  PACKING  Op.Bal.  Receipt  Total  Issue  Closing  MSR-Price

    The Shelf-ID and Tax-Rate columns sit between the product name and the PACKING
    token, so _split_product_numbers absorbs them into the product-text region.
    The popped numeric tail is therefore exactly the 6 trailing measure columns:
        vals[0]=Op.Bal   vals[1]=Receipt   vals[2]=Total(=Op+Receipt, ignored)
        vals[3]=Issue    vals[4]=Closing   vals[5]=MSR price (ignored)

    There are no purchase_return / sales_return columns, so reconciliation is
    Closing = Op.Bal + Receipt - Issue.
    """
    records = []
    for line in text.splitlines():
        s = line.strip()
        if _skip_line(s):
            continue
        prod, tail, exp = _split_product_numbers(s)
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
            "sales_qty": vals[3],
            "closing_stock": vals[4],
        }
        if exp:
            r["expiry"] = exp
        records.append(r)
    return records
