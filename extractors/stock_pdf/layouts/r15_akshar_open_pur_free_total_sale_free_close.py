from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_numbers_comma as _split_product_numbers,
    _split_product_pack,
)


def parse_akshar_open_pur_free_total_sale_free_close(text):
    """AKSHAR MEDICINES 'Stock Statement Report' (Non Moving Products) — 7 movement
    columns with dedicated Purchase-Free and Sales-Free cells plus a printed Total
    cross-check:

      Product | Opening | Purchase | Purchase Free | Total | Sales | Sales Free | Closing

    (The header renders glued/garbled as
     'Product Opening Purchase Purchase FreTeotal Sales Sales Free Closing Stock',
     compact 'purchasepurchasefreteotalsales…' — the gate token below.)

    Each product row carries exactly 7 trailing numbers; embedded pack tokens
    ('1*3', '10*10', '18%') are not numeric so they stay in the product name and do
    NOT pollute the tail. The coarse simple4 fallback pops only the first 4 numbers
    (Opening/Purchase/PurchaseFree/Total) — mapping the Total cross-check into
    closing_stock and dropping Sales/SalesFree/real Closing -> ~38% false SANITY.

    Mapping:
      vals[0]=Opening, vals[1]=Purchase, vals[2]=Purchase Free,
      vals[3]=Total (=Op+Pur+PurFree cross-check, IGNORED),
      vals[4]=Sales, vals[5]=Sales Free, vals[6]=Closing.
    Reconciles: closing = opening + purchase + purchase_free - sales - sales_free.
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
        if len(vals) < 7:
            continue
        # Take the LAST 7 numeric cells (a stray leading pack digit, if any survived
        # tokenization, folds back into the name).
        core = vals[-7:]
        if len(vals) > 7:
            lead = vals[:-7]
            lead_toks = [
                str(int(x)) if x == int(x) else str(x) for x in lead
            ]
            prod = (prod + " " + " ".join(lead_toks)).strip()
        name, pack = _split_product_pack(prod)
        r = {
            "product_name": name,
            "pack": pack,
            "opening_stock": core[0],
            "purchase_stock": core[1],
            "purchase_free": core[2],
            # core[3] = printed Total (Op+Pur+PurFree cross-check) — intentionally dropped
            "sales_qty": core[4],
            "sales_free": core[5],
            "closing_stock": core[6],
        }
        if exp:
            r["expiry"] = exp
        records.append(r)
    return records
