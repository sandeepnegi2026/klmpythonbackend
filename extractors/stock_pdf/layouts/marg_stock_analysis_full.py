from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_numbers_comma as _split_product_numbers,
    _split_product_pack,
)


def parse_marg_stock_analysis_full(text):
    """Marg 'STOCK & SALES ANALYSIS' full-movement layout (SIDDHIVINAYAK style).

    Two-line header, 14 numeric columns + a trailing M.EXP (month/year expiry):

        ITEM | OPENING | PURCHASE     | S/R      | REPL/OTHER | TOTAL | SALES        | SAMPLE | P/R | REPL/OTHER | CLOSING | M.EXP
               STOCK[0]  QTY[1] FREE[2] QTY[3] .. [4] [5]      STOCK[6] QTY[7] FREE[8] [9]     T/F[10] [11] [12]  STOCK[13]

    TOTAL(6) = OPENING(0) + every inflow(1..5); CLOSING(13) = TOTAL - every outflow(7..12).
    Verified on all 281 SIDDHIVINAYAK rows.

    We fold every secondary inflow (purchase-free, S/R, repl, other) into purchase_stock
    and every secondary outflow (sales-free, sample, P/R, repl, other) into sales_qty —
    the marg_open_pur_free_sale precedent. Two reasons: (1) canonical has no field for
    repl/sample/other; (2) core.enforce_schema rounds every stock number to an integer, and
    this vendor prints HALF-unit free goods (e.g. sales 6.5 + free 0.5). Rounding the columns
    separately would drop the paired halves (6.5->6, 0.5->0) and break reconciliation, but
    OPENING/TOTAL/CLOSING are whole units, so inflows(=TOTAL-OPENING) and outflows(=TOTAL-CLOSING)
    are integers — folding keeps them exact. Then closing = opening + purchase_stock - sales_qty.
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
        if len(vals) < 14:
            continue
        v = vals[-14:]  # guard against a stray leading number in the tail
        name, pack = _split_product_pack(prod)
        r = {
            "product_name": name,
            "pack": pack,
            "opening_stock": v[0],
            "purchase_stock": v[1] + v[2] + v[3] + v[4] + v[5],  # all inflows (= TOTAL - OPENING)
            "purchase_return": 0.0,
            "total_stock": v[6],
            "sales_qty": v[7] + v[8] + v[9] + v[10] + v[11] + v[12],  # all outflows (= TOTAL - CLOSING)
            "sales_return": 0.0,
            "closing_stock": v[13],
        }
        if exp:
            r["expiry"] = exp
        records.append(r)
    return records
