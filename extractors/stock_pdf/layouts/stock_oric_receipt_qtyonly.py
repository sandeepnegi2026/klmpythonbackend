from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_numbers,
    _split_product_pack,
)


def _reconciles(vals, o):
    """opening + receipt - issue == closing at alignment offset ``o`` (2% tol).

    Column order for this qty-only-Receipt variant (7 numeric cells):
        OPENING(q, v) RECEIPT(q) ISSUE(q, v) CLOSING(q, v)
    so the qty stock identity uses offsets o(open q), o+2(receipt q),
    o+3(issue q) and o+5(closing q) — RECEIPT contributes only a qty, no value.
    """
    if len(vals) < o + 7:
        return False
    return abs((vals[o] + vals[o + 2] - vals[o + 3]) - vals[o + 5]) <= max(
        abs(vals[o + 5]), 1.0
    ) * 0.02


def parse_stock_oric_receipt_qtyonly(text):
    """Marg 'STOCK & SALES ANALYSIS' — qty-only-Receipt variant (AMRITA TRADING COSMOCOR).

    Same banner family as ``stock_oric_pairs`` but the RECEIPT group carries a
    QTY column ONLY (no value), while OPENING / ISSUE / CLOSING are qty+value
    pairs. Sub-header::

        ITEM DESCRIPTION OPENING RECEIPT ISSUE CLOSING
                         QTY. VALUE QTY. QTY. VALUE QTY. VALUE

    So each product row carries exactly SEVEN trailing numbers::

        OPENING(q0, v1)  RECEIPT(q2)  ISSUE(q3, v4)  CLOSING(q5, v6)

    stock_oric_pairs expects EIGHT (a paired Receipt value at index 3), so it
    reads ISSUE-qty into purchase_value and shifts CLOSING off the row end,
    collapsing sanity to 0.0. This parser maps the seven cells directly:
        OPENING QTY  -> opening_stock
        OPENING VALUE-> opening_value
        RECEIPT QTY  -> purchase_stock   (qty only; no purchase_value column)
        ISSUE QTY    -> sales_qty
        ISSUE VALUE  -> sales_value
        CLOSING QTY  -> closing_stock
        CLOSING VALUE-> closing_stock_value

    A division band ("COSMOCOR") has no numeric tail and the grand-total footer
    ("TOTAL ...") is caught by _skip_line, so both are dropped.
    """
    records = []
    for line in text.splitlines():
        s = line.strip()
        if _skip_line(s):
            continue
        prod, tail, exp = _split_product_numbers(s)
        if not prod or len(tail) < 7:
            continue
        name, pack = _split_product_pack(prod)
        vals = _nums(tail)
        if len(vals) < 7:
            continue
        # A mangled bare-number pack (e.g. "1" left from a "1*30" pack) is popped
        # into the numeric tail as a stray leading value, shifting every column
        # one to the right. If the default alignment fails the
        # opening+receipt-issue=closing identity but a one-value left shift
        # satisfies it, drop that stray leading value.
        offset = (
            1
            if (not _reconciles(vals, 0) and len(vals) > 7 and _reconciles(vals, 1))
            else 0
        )
        v = vals[offset:]
        r = {
            "product_name": name,
            "pack": pack,
            "opening_stock": v[0],
            "opening_value": v[1],
            "purchase_stock": v[2],
            "sales_qty": v[3],
            "sales_value": v[4],
            "closing_stock": v[5],
            "closing_stock_value": v[6] if len(v) > 6 else 0.0,
        }
        if exp:
            r["expiry"] = exp
        records.append(r)
    return records
