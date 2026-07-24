from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_numbers,
    _split_product_pack,
)


def parse_marg_pds_replace(text):
    """Marg/KLM 'PRODUCT DESCRIPTION ... REPLACE+' stock-position (receipts) statement.

    Header:
        PRODUCT DESCRIPTION | OPENING STOCK | PURCHASE QUANTITY |
        SALE RETURN QUANTITY | REPLACE+ OTHERS | TOTAL RECEIVE

    There is no sales-out column. TOTAL is the closing stock and equals the sum
    of every receipt column:  TOTAL = OPENING + PURCHASE + SALE_RETURN + REPLACE.

    Each data row carries exactly 5 numeric columns:
        vals[0] = opening_stock
        vals[1] = purchase quantity
        vals[2] = sale-return quantity (goods returned IN, additive)
        vals[3] = replace+ receive    (additive IN)
        vals[4] = TOTAL / closing_stock

    To satisfy the canonical reconciliation equation
        closing = opening + purchase - purchase_return - sales + sales_return
    the REPLACE+ column is folded into purchase_stock (both are stock IN), the
    sale-return column maps to sales_return, and sales_qty / purchase_return are 0.
    """
    records = []
    for line in text.splitlines():
        s = line.strip()
        if _skip_line(s):
            continue
        prod, tail, exp = _split_product_numbers(s)
        if not prod:
            continue
        vals = _nums(tail)
        if len(vals) < 5:
            continue
        name, pack = _split_product_pack(prod)
        r = {
            "product_name": name,
            "pack": pack,
            "opening_stock": vals[0],
            "purchase_stock": vals[1] + vals[3],  # purchase qty + REPLACE+ receive (both IN)
            "purchase_return": 0.0,
            "sales_qty": 0.0,
            "sales_return": vals[2],
            "closing_stock": vals[4],
        }
        if exp:
            r["expiry"] = exp
        records.append(r)
    return records
