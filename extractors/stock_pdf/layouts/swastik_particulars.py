from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_numbers,
    _split_product_pack,
)


def parse_swastik_particulars(text):
    """Particulars/Misc stock statement (ERP 'All Item Report').

    Two-line header:
        Particulars Pkg. Open. Purch. Sales Sales Misc Close Closing Sales
                         Qty.  Qty.        Ret.&DC.Out      Stock Value Value

    Pkg. is alphabetic ('50 GM', 'CAP', 'TAB 10S') and is folded into the
    product name by _split_product_pack, leaving 8 numeric tail columns:

        vals[0] opening_stock
        vals[1] purchase_stock
        vals[2] sales_return        (the 'Sales Ret. & DC. Out' sub-column)
        vals[3] sales_qty           (the 'Sales' sub-column)
        vals[4] misc                (ignored)
        vals[5] closing_stock
        vals[6] closing_stock_value
        vals[7] sales_value

    Reconciliation: closing = opening + purchase - sales_qty + sales_return
    (no purchase_return column). The duplicated 'Sales' pair is ordered
    RETURN then QTY, not QTY then RETURN.

    A numeric pack count can leak into vals[0] (e.g. 'OXIDOX CAP' strength
    10 -> a 9-value row). Detected by len(vals) >= 9 and corrected with a
    +1 offset so every field shifts right by one.
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
        if len(vals) < 8:
            continue
        name, pack = _split_product_pack(prod)
        # 9-value rows: a numeric pack count leaked as vals[0]; shift right.
        off = 1 if len(vals) >= 9 else 0
        if off + 7 >= len(vals) + 1:  # guard: not enough columns after shift
            off = 0
        if off + 6 > len(vals) - 1:
            continue
        r = {
            "product_name": name,
            "pack": pack,
            "opening_stock": vals[off + 0],
            "purchase_stock": vals[off + 1],
            "sales_return": vals[off + 2],
            "sales_qty": vals[off + 3],
            "closing_stock": vals[off + 5],
            "closing_stock_value": vals[off + 6],
            "sales_value": vals[off + 7] if off + 7 < len(vals) else 0.0,
        }
        if exp:
            r["expiry"] = exp
        records.append(r)
    return records
