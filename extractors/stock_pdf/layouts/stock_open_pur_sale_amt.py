from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_numbers_comma as _split_product_numbers,
    _split_product_pack,
)


def parse_stock_open_pur_sale_amt(text):
    """KLM stock register (Rohtak/Friends style).

    Columns: ITEM  OPENING  PURCHASE  SALE  AMOUNT-I  CL.STOCK  AMOUNT-II
             [NEAR EXP.  N.E.VALUE]
    closing = CL.STOCK (vals[4]); vals[3]/vals[5] are rupee amounts.

    Two B/E/PR variants (KHATTAR PHARMA, MUNISH MEDICOSE) insert breakage/expiry
    (and, for KHATTAR, an extra Sale-Return) columns between PURCHASE and SALE, so
    the fixed positions shift right. The header carries 'B/E/PR' (and 'SALE RET.' for
    the 8-fixed KHATTAR shape); both bind FRONT positions and drop the optional
    trailing NEAR EXP./N.E.VALUE pair and the final %SALE (source balances exactly:
    OPENING + PURCHASE - B/E/PR - SALE = CL.STOCK).
    """
    low = text.lower()
    be_pr = "b/e/pr" in low
    khattar = be_pr and ("sale ret" in low or "saleret" in low.replace(" ", ""))
    min_len = 8 if khattar else (7 if be_pr else 5)

    records = []
    for line in text.splitlines():
        s = line.strip()
        if _skip_line(s):
            continue
        prod, tail, exp = _split_product_numbers(s)
        if not prod or len(tail) < min_len:
            continue
        name, pack = _split_product_pack(prod)
        vals = _nums(tail)
        if len(vals) < min_len:
            continue
        if khattar:
            # ITEM OPENING PURCHASE SALE-RET B/E/PR SALE AMOUNT-I CL.STOCK AMOUNT-II ...
            r = {
                "product_name": name, "pack": pack,
                "opening_stock": vals[0],
                "purchase_stock": vals[1],
                "sales_return": vals[2],
                "purchase_return": vals[3],
                "sales_qty": vals[4],
                "sales_value": vals[5],
                "closing_stock": vals[6],
                "closing_stock_value": vals[7],
            }
        elif be_pr:
            # ITEM OPENING PURCHASE B/E/PR SALE AMOUNT-I CL.STOCK AMOUNT-II ...
            r = {
                "product_name": name, "pack": pack,
                "opening_stock": vals[0],
                "purchase_stock": vals[1],
                "purchase_return": vals[2],
                "sales_qty": vals[3],
                "sales_value": vals[4],
                "closing_stock": vals[5],
                "closing_stock_value": vals[6],
            }
        else:
            r = {
                "product_name": name,
                "pack": pack,
                "opening_stock": vals[0],
                "purchase_stock": vals[1],
                "sales_qty": vals[2],
                "sales_value": vals[3],
                "closing_stock": vals[4],
                "closing_stock_value": vals[5] if len(vals) > 5 else 0.0,
            }
        if exp:
            r["expiry"] = exp
        records.append(r)
    return records
