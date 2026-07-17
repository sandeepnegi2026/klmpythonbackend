from extractors.stock_pdf.constants import NUM_RE
from extractors.stock_pdf.parse_common import (
    _skip_line,
    _split_product_pack,
    _to_number,
)


def parse_stock_lstsl(text):
    """Busy/Tally 'Stock & Sales Report for the month' — 7-column LstSL variant
    (MAHESH AGENCIES).

    Header: Product Name | Pack | LstSL | Open | Recd. | Sales | Close |
            Order | Pend
    — exactly SEVEN numeric cells after the product/pack text, no trailing
    Stk.Value / LstMove (those siblings route to saraswati_lstsl). Blanks
    print as '-', Order is often negative. The coarse simple4 parse shifts
    every mapping one cell left (opening<-LstSL, sales<-Recd.), hence this
    dedicated parser.

    Reconciles: Close = Open + Recd - Sales (ARGICYNE: 35+250-90=195). The
    footer prints only labelled VALUE lines (comma-grouped -> not NUM_RE) and
    the appended "INVOICES TAKEN IN RECEIPT" ledger rows end in a date token,
    so both self-skip. Names may carry a leading '*' (near-expiry) / '#'
    (scheme) marker.
    """
    records = []
    for line in text.splitlines():
        s = line.strip().lstrip('*# ')
        if _skip_line(s):
            continue
        low = s.lower()
        if "product name" in low or set(s) <= set("- "):
            continue
        toks = s.split()
        if len(toks) < 8:
            continue
        run = []
        while toks and NUM_RE.match(toks[-1]) and len(run) < 7:
            run.insert(0, toks.pop())
        if len(run) != 7 or not toks:
            continue
        stats = [_to_number(t) or 0.0 for t in run]
        # [0] LstSL  [1] Open  [2] Recd.  [3] Sales  [4] Close  [5] Order  [6] Pend
        opening, recd, sales, close = stats[1], stats[2], stats[3], stats[4]
        if opening == 0 and recd == 0 and sales == 0 and close == 0:
            continue
        name, pack = _split_product_pack(" ".join(toks))
        records.append({
            "product_name": name,
            "pack": pack,
            "opening_stock": opening,
            "purchase_stock": recd,
            "sales_qty": sales,
            "closing_stock": close,
        })
    return records
