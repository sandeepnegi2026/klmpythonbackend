from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_numbers,
    _split_product_pack,
)


def _reconciles(vals, o):
    """opening + receipt - issue == closing at alignment offset `o` (2% tol)."""
    if len(vals) < o + 7:
        return False
    return abs((vals[o] + vals[o + 2] - vals[o + 4]) - vals[o + 6]) <= max(abs(vals[o + 6]), 1.0) * 0.02


def parse_stock_oric_pairs(text):
    """Marg 'Stock & Sales Analysis' — Opening/Receipt/Issue/Closing as qty+value pairs.

    Header: ITEM DESCRIPTION OPENING RECEIPT ISSUE CLOSING [DUMP]
            QTY. VALUE  QTY. VALUE  QTY. VALUE  QTY. VALUE  [QTY.]
    columns: OPEN(q0,v1) RECEIPT(q2,v3) ISSUE(q4,v5) CLOSING(q6,v7) [DUMP q8]
    Distinct from value_pairs (no rate column) and qty_value_total (no Total col).
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
        # A mangled bare-number pack (e.g. "1" left from "1*30GM") is popped into the
        # numeric tail as an extra leading value, shifting every column right. If the
        # default alignment fails the opening+receipt-issue=closing identity but a
        # one-value left shift satisfies it, drop that stray leading value.
        offset = 1 if (not _reconciles(vals, 0) and len(vals) > 8 and _reconciles(vals, 1)) else 0
        # Trailing digits of the product NAME plus a mangled bare-number pack
        # (e.g. "KLM C 1000 10", "KLM-FX 180 10") are popped into the numeric
        # tail as TWO extra leading integers, fabricating opening qty/value and
        # hijacking the row's real numbers (GLOBE ENTERPRISE KLMMAYSALESTOCK).
        # Only when the 0- and 1-shift alignments both fail the identity, a
        # 2-shift satisfies it, and both stray tokens are bare integers, return
        # the name digit to the product (dropping the bare pack, same treatment
        # as the 1-shift above) and realign.
        if (
            offset == 0
            and len(vals) > 9
            and len(vals) == len(tail)
            and not _reconciles(vals, 0)
            and not _reconciles(vals, 1)
            and _reconciles(vals, 2)
            and tail[0].isdigit()
            and tail[1].isdigit()
        ):
            name, pack = _split_product_pack(prod + " " + tail[0])
            offset = 2
        v = vals[offset:]
        r = {
            "product_name": name,
            "pack": pack,
            "opening_stock": v[0],
            "opening_value": v[1],
            "purchase_stock": v[2],
            "purchase_value": v[3],
            "sales_qty": v[4],
            "sales_value": v[5],
            "closing_stock": v[6],
            "closing_stock_value": v[7] if len(v) > 7 else 0.0,
        }
        if exp:
            r["expiry"] = exp
        records.append(r)
    return records
