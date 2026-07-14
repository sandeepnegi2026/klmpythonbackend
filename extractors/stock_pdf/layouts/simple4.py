from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_numbers,
    _split_product_pack,
)


def parse_simple4(text):
    """Busy/Tally Simple4: product OPENING RECEIPT ISSUE CLOSING [M.EXP]"""
    records = []
    for line in text.splitlines():
        s = line.strip()
        if _skip_line(s):
            continue
        prod, tail, exp = _split_product_numbers(s)
        if not prod or len(tail) < 4:
            continue
        name, pack = _split_product_pack(prod)
        vals = _nums(tail)
        if len(vals) < 4:
            continue
        # A bare pack digit in the product name (e.g. "NIOFINE.TAB 7", "TECUM 0-1% 1")
        # gets popped into the numeric tail by _split_product_numbers, so a 5-number tail
        # binds vals[0:4] one slot LEFT. When the standard 4-window fails the reconcile
        # (opening + receipt - issue != closing) but the shifted window balances, the
        # leading integer is a pack count: use vals[-4:] and fold it back into the name.
        # The documented [M.EXP] 5th-column variant reconciles on vals[0:4], so it is kept.
        if len(vals) == 5 and not exp:
            v = vals
            first_ok = abs((v[0] + v[1] - v[2]) - v[3]) < 0.5
            last_ok = abs((v[1] + v[2] - v[3]) - v[4]) < 0.5
            if last_ok and not first_ok:
                lead = v[0]
                lead_tok = str(int(lead)) if lead == int(lead) else str(lead)
                name = f"{name} {lead_tok}".strip()
                vals = v[1:]
        r = {
            "product_name": name,
            "pack": pack,
            "opening_stock": vals[0],
            "purchase_stock": vals[1],
            "sales_qty": vals[2],
            "closing_stock": vals[3],
        }
        if exp:
            r["expiry"] = exp
        records.append(r)
    return records
