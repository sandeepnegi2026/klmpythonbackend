from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_numbers,
    _split_product_pack,
)


def _group_cols(seq, rate):
    """Group a flat number list into (qty, value) columns.

    A full column is two numbers where value ~= qty * rate (8% tol). When the value
    sub-column is 0 it is dropped by the ERP, leaving a lone qty -> (qty, 0.0).
    """
    cols = []
    i = 0
    n = len(seq)
    while i < n:
        q = seq[i]
        v = 0.0
        if i + 1 < n:
            nxt = seq[i + 1]
            pred = q * rate
            if abs(pred) > 0.5 and abs(nxt - pred) / max(abs(pred), 1.0) <= 0.08:
                v = nxt
                i += 2
                cols.append((q, v))
                continue
        cols.append((q, 0.0))
        i += 1
    return cols


def _reconciles(o, p, s, r, c):
    return abs((o + p - s + r) - c) / max(abs(c), 1.0) <= 0.05


def parse_nagendra_rate_pairs(text):
    """Stock statement: leading RATE column then 5 Qty/Value pairs.

    Header: Product Pack Rate | Opening(Qty Val) | Purchase(Qty Val) | Sales(Qty Val)
            | Free/Retn(Qty Val) | Closing(Qty Val) | (last-month-sale)
    Equation: closing = opening + purchase - sales + free/retn  (Free/Retn = sales_return).

    Columns collapse per row: a pair whose VALUE rounds to 0 drops its value sub-column
    (lone qty); a whole pair (Purchase / Free-Retn) is omitted when its qty is 0. So column
    counts vary (6..12). We anchor on a fixed structure:
      vals[0] = rate, vals[-1] = last-month sale (ignored),
      opening = (vals[1], vals[2])  (always a full pair; opening value may differ from rate),
      the remaining numbers are grouped by rate into columns; the LAST is Closing and the
      middle columns are an ordered subset of {Purchase, Sales, Free/Retn}, disambiguated
      by the reconciliation equation.
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
        # need at least rate + opening pair + one more col + last-month = 5 numbers,
        # and the middle (vals[1:-1]) must hold the opening pair + >=1 col -> len(mid) >= 3
        if len(vals) < 5:
            continue
        rate = vals[0]
        mid = vals[1:-1]
        if len(mid) < 3:
            continue
        opening = (mid[0], mid[1])
        rest_cols = _group_cols(mid[2:], rate)
        if len(rest_cols) < 1:
            continue
        closing = rest_cols[-1]
        mids = rest_cols[:-1]
        nm = len(mids)

        # candidate (purchase_col, sales_col, retn_col); None => 0
        cands = []
        if nm == 0:
            cands.append((None, None, None))
        elif nm == 1:
            cands.append((None, mids[0], None))        # Sales only (typical)
            cands.append((mids[0], None, None))        # Purchase only
        elif nm == 2:
            a, b = mids
            cands.append((a, b, None))                 # Purchase, Sales
            cands.append((None, a, b))                 # Sales, Free/Retn
        elif nm == 3:
            cands.append((mids[0], mids[1], mids[2]))   # Purchase, Sales, Free/Retn
        else:
            # more columns than the layout allows -> map first/second/third by position
            cands.append((mids[0], mids[1], mids[2]))

        chosen = None
        for pc, sc, rc in cands:
            pQ = pc[0] if pc else 0.0
            sQ = sc[0] if sc else 0.0
            rQ = rc[0] if rc else 0.0
            if _reconciles(opening[0], pQ, sQ, rQ, closing[0]):
                chosen = (pc, sc, rc)
                break
        if chosen is None:
            chosen = cands[0]  # fall back to the most-likely layout even if it didn't reconcile
        pc, sc, rc = chosen

        name, pack = _split_product_pack(prod)
        r = {
            "product_name": name,
            "pack": pack,
            "rate": rate,
            "opening_stock": opening[0],
            "opening_value": opening[1],
            "purchase_stock": pc[0] if pc else 0.0,
            "purchase_value": pc[1] if pc else 0.0,
            "sales_qty": sc[0] if sc else 0.0,
            "sales_value": sc[1] if sc else 0.0,
            "sales_return": rc[0] if rc else 0.0,
            "closing_stock": closing[0],
            "closing_stock_value": closing[1],
        }
        if exp:
            r["expiry"] = exp
        records.append(r)
    return records
