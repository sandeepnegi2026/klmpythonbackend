from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_numbers,
    _split_product_pack,
)


def parse_capital_stock_sale_stmt(text):
    """KLM 'Sales & Stock Statement' — Op.Bal/Receipt/Total/Issue/Closing (qty only).

    Header (CAPITAL PHARMA AGENCIES, one row per KLM division — COSMO Q, etc.):
        PRODUCT NAME  PACKING  Op.Bal.  Receipt  Total  Issue  Closing
                               Qty.     Qty.     Qty.   Qty.   Balance

    Exactly FIVE trailing qty columns per row:
        vals[0]=Op.Bal   vals[1]=Receipt   vals[2]=Total (= Op.Bal + Receipt, ignored)
        vals[3]=Issue    vals[4]=Closing Balance

    There are no value/return columns, so reconciliation is
        Closing = Op.Bal + Receipt - Issue.

    A non-numeric PACKING token (e.g. "30ML", "TAB 10,S") always separates the
    product name from the five measures, so _split_product_numbers pops exactly the
    trailing qty run and leaves name-embedded numbers (CETALORE 5, EBERFINE CREAM
    15GM) intact.

    Distinct from the DISA sibling (disa_opbal_receipt_total_issue) which carries
    extra Shelf-ID / Tax-Rate / MSR-Price columns (six numbers per row): this KLM
    export has NONE of those — exactly five numbers per row.
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
