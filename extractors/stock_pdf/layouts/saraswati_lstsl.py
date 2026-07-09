import re

from extractors.stock_pdf.constants import NUM_RE
from extractors.stock_pdf.parse_common import (
    _skip_line,
    _split_product_pack,
    _to_number,
)


def parse_saraswati_lstsl(text):
    """Busy/Tally 'Stock & Sales Report' with a LstMove date column.

    Header: Product Name | Pack | LstSL | Open | Recd. | Sales | Close |
            Order | Pend | LstMove | Stk.Value

    The LstMove column is a dd/mm/yy date (or the artefact '/ /') sitting
    between the stat columns and Stk.Value, which breaks the usual
    trailing-number popping.  We anchor from the right instead:
      1. pop the trailing Stk.Value (a number)
      2. drop the '/'-bearing LstMove token(s)
      3. take the trailing run of numeric/dash tokens and keep the LAST 7
         of them as the stat columns (LstSL Open Recd Sales Close Order Pend)
    Any extra leading numbers in that run belong to the pack (e.g. 'TAB 10')
    and are folded back into the product text so the fixed index mapping
    never shifts.

    Reconciles: Close = Open + Recd - Sales  (no purchase/sales return cols).
    """
    records = []
    for line in text.splitlines():
        s = line.strip()
        if _skip_line(s):
            continue
        low = s.lower()
        if "product name" in low or set(s) <= set("- "):
            continue
        toks = s.split()
        if len(toks) < 5:
            continue
        # 1. trailing Stk.Value must be a number
        if not NUM_RE.match(toks[-1]):
            continue
        stkval = _to_number(toks[-1]) or 0.0
        toks = toks[:-1]
        # 2. drop the LstMove date column: 'dd/mm/yy' (one token) or '/ /' -> ['/','/']
        while toks and "/" in toks[-1]:
            toks.pop()
        # 3. trailing run of numeric / dash tokens
        run = []
        while toks and NUM_RE.match(toks[-1]):
            run.insert(0, toks[-1])
            toks.pop()
        if len(run) < 7:
            continue
        stats = [_to_number(t) or 0.0 for t in run[-7:]]  # last 7 = real stat cols
        extra = run[:-7]                                  # leading nums -> pack
        if not toks:
            continue
        name, pack = _split_product_pack(" ".join(toks + extra))
        opening = stats[1]
        recd = stats[2]
        sales = stats[3]
        close = stats[4]
        # drop all-zero phantom rows
        if opening == 0 and recd == 0 and sales == 0 and close == 0:
            continue
        records.append({
            "product_name": name,
            "pack": pack,
            "opening_stock": opening,
            "purchase_stock": recd,
            "sales_qty": sales,
            "closing_stock": close,
            "closing_stock_value": stkval,
        })
    return records
