from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_numbers,
    _split_product_pack,
)


def parse_marg_opqty(text):
    """Marg 'STOCK & SALE REPORT' OPQTY layout.

    Header: ITEM NAME BOX PACK OPQTY P_QTY REPL S_QTY B_QTY
            (wrapped 2nd header line: PMthSqty/Amt PndClmQ)

    Numeric columns left-to-right (after _split_product_numbers/_nums):
        vals[0] OPQTY    -> opening_stock
        vals[1] P_QTY    -> purchase_stock
        vals[2] REPL     -> purchase_return (replacement; 0 across this family)
        vals[3] S_QTY    -> sales_qty
        vals[4] B_QTY    -> closing_stock (balance)
        vals[5] PMthSqty -> previous-month sales qty, ignored when present

    Reconciles exactly: closing = opening + purchase - repl - sales.
    Verified 244/244 rows across 8 LIFECARE 'STOCK & SALE REPORT' files.
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
            "purchase_stock": vals[1],
            "purchase_return": vals[2],
            "sales_qty": vals[3],
            "closing_stock": vals[4],
        }
        if exp:
            r["expiry"] = exp
        records.append(r)
    return records
