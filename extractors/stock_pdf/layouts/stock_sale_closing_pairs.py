"""Marg 'STOCK & SALES ANALYSIS' — reduced 2-group SALE/CLOSING qty+value pairs.

Grouped header (two lines):

    <===SALE===>  <==CLOSING==>
    ITEM DESCRIPTION  QTY. VALUE  QTY. VALUE

This is the 2-group sibling of stock_oric_pairs (Open/Receipt/Issue/Closing).
This vendor's export (SRI RAGHUNATH MEDICAL, "KLM ALL SALE / STOCK") drops the
Opening and Purchase/Receipt columns entirely, so each data row is just

    <product+pack>  SALE_QTY  SALE_VALUE  CLOSING_QTY  CLOSING_VALUE

i.e. exactly 4 trailing numbers. Division bands ("KLM COSMO DIVISION P"),
per-division "Total"/"TOTAL" footers, separators and the header are dropped by
the shared _skip_line (which already skips "KLM " bands and Total rows).

Opening / purchase / free / return are legitimately absent from this report, so
they are left at 0.0; closing_stock carries the real closing quantity. The
closing = opening + purchase - sales sanity is therefore not meaningful here and
will be a no-op (opening/purchase are 0), which is correct for this layout.
"""
from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_numbers,
    _split_product_pack,
)


def parse_stock_sale_closing_pairs(text):
    records = []
    for line in text.splitlines():
        s = line.strip()
        if _skip_line(s):
            continue
        prod, tail, exp = _split_product_numbers(s)
        if not prod:
            continue
        vals = _nums(tail)
        # Need at least the 4 SALE/CLOSING numbers. Take the LAST 4 so a stray
        # bare-number pack token that leaked into the tail (rare) does not shift
        # the real columns rightward.
        if len(vals) < 4:
            continue
        v = vals[-4:]
        name, pack = _split_product_pack(prod)
        r = {
            "product_name": name,
            "pack": pack,
            "opening_stock": 0.0,
            "purchase_stock": 0.0,
            "purchase_free": 0.0,
            "sales_qty": v[0],
            "sales_value": v[1],
            "sales_free": 0.0,
            "sales_return": 0.0,
            "closing_stock": v[2],
            "closing_stock_value": v[3],
        }
        if exp:
            r["expiry"] = exp
        records.append(r)
    return records
