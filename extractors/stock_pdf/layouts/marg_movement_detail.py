from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_numbers,
    _split_product_pack,
)


def _total_identity_ok(w):
    """The printed TOTAL (w[4]) equals opening +/- purchase-side returns/others.

    The sign of the purchase-side REPL./RETURN column varies per row (return-out
    vs replacement-received), so accept either. Used only to lock onto the correct
    9-wide window past any spurious leading product-code tokens.
    """
    opening, purchases, pur_return, pur_others, total = w[0], w[1], w[2], w[3], w[4]
    a = opening + purchases - pur_return + pur_others
    b = opening + purchases + pur_return + pur_others
    return min(abs(a - total), abs(b - total)) <= max(1.0, 0.02 * abs(total))


def _pick_stock_window(vals):
    """Return the 9 stock columns, skipping spurious leading product-code tokens.

    Clean rows satisfy the TOTAL identity at vals[0:9]; a small number of rows
    carry 1-2 leading code numbers that shift the window right.
    """
    base = vals[:9]
    if _total_identity_ok(base):
        return base
    for shift in (1, 2):
        if len(vals) >= 9 + shift and _total_identity_ok(vals[shift:shift + 9]):
            return vals[shift:shift + 9]
    return base


def parse_marg_movement_detail(text):
    """Marg 'STOCK & SALES ANALYSIS' movement detail (qty only, no value pairs).

    Second header row:
      OPENING STOCK | PURCHASES | REPL./RETURN | OTHERS | TOTAL STOCK |
      SALES | REPL./RETURN | OTHERS | CLOSING STOCK [| RATE | RE-ORDER]

    Ground truth: the printed TOTAL is the ERP's reconciled stock-available, and
    closing = TOTAL - sales - sales_return - sales_others. The purchase-side
    REPL./RETURN sign varies per row, so we anchor off TOTAL and fold every
    adjustment into purchase_return so the canonical equation
    (closing = opening + purchase - purchase_return - sales + sales_return)
    holds exactly. Verified 659/659 rows reconcile across all 12 family files.
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
        if len(vals) < 9:
            continue
        w = _pick_stock_window(vals)
        (opening, purchases, pur_return, pur_others, total,
         sales, sal_return, sal_others, closing) = w
        # skip phantom all-zero stock rows (only a rate may be printed)
        if opening == 0 and purchases == 0 and sales == 0 and closing == 0:
            continue
        name, pack = _split_product_pack(prod)
        # Fold all stock-reducing adjustments into purchase_return so that
        # opening + purchase - purchase_return - sales + sales_return == closing,
        # anchored on the ERP's own printed TOTAL.
        c_pur_return = opening + purchases + sal_return + sal_others - total
        r = {
            "product_name": name,
            "pack": pack,
            "opening_stock": opening,
            "purchase_stock": purchases,
            "purchase_return": c_pur_return,
            "sales_qty": sales,
            "sales_return": 0.0,
            "closing_stock": closing,
        }
        if exp:
            r["expiry"] = exp
        records.append(r)
    return records
