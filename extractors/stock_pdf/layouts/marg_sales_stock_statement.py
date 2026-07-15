import re

from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_numbers,
    _split_product_pack,
)


def parse_marg_sales_stock_statement(text):
    """Marg 'Sales & Stock Statement' — header-driven NARROW + WIDE variants.

    Two exports of the SAME Marg family (banner
    "Page No.1 Sales & Stock Statement(From .. Upto ..)"), division-banded
    ("KLM DERMA DIV.", "KLM LABORATORIES"). Both print a two-line column header;
    the number of Qty/Value column groups differs, so this parser is gated by the
    trailing-number COUNT per row (fixed for each variant) and maps positionally.

    NARROW (KAMLAWATI ENTERPRISES) — 11 trailing numbers/row:
        PRODUCT NAME  PACKING
        [0] Op.Qty  [1] Opening-Bal Value
        [2] Receipt-Qty  [3] Receipt/Pur Value
        [4] Total-Qty  (= Op + Receipt, cross-check, ignored)
        [5] Issue-Qty  [6] Issue/Sales Value
        [7] Closing-Qty  [8] Closing-Bala Value
        [9] Near-Expiry  [10] MSR-Price
      Reconciles: Closing = Op + Receipt - Issue.

    WIDE (KALYANI PHARMA) — 15 trailing numbers/row (extra Return + Expiry groups):
        PRODUCT NAME  ShelfID  PACKING
        [0] Op.Qty  [1] Op Value
        [2] Receipt-Qty  [3] Receipt Value
        [4] Ret(ReturnToCOM)-Qty  [5] Value        -> purchase_return (outflow)
        [6] Total-Qty  (cross-check, ignored)
        [7] Issue-Qty  [8] Issue/Sales Value
        [9] RetFromCustomer-Qty  [10] Value         -> sales_return (inflow)
        [11] Expiry/Breakage-Qty  [12] Value        -> exp_damage (outflow, not in eqn)
        [13] Closing-Qty  [14] Closing-Bala Value
      Reconciles: Closing = Op + Receipt - RetToCOM - Issue + RetFromCustomer
                            - Expiry/Breakage.

    A non-numeric PACKING token (e.g. "1 X30GM", "30 GM", "10 TAB") separates the
    product name from the trailing measures, so _split_product_numbers pops the
    number run and leaves name-embedded numbers (EBERFINE CREAM 15G, KLM C-1000)
    intact. When a glued packing digit leaks into the tail (KAMLAWATI's
    "KENZ-SAL LOTION 1 1 …" gives 13 tokens), the LAST N numbers are the movement
    columns, so we take vals[-N:].

    Both variants map Qty -> qty fields and Value -> *_value fields; a printed
    Value column is NEVER placed in a qty field (the bug that made these files
    mis-detect to qty_value_total / stock_simple_7col and fail sanity).
    """
    low = text.lower()
    comp = low.replace(" ", "")
    # WIDE variant carries the ReturnToCOM + RetFromCustomer/Expiry column groups.
    is_wide = "retreturntocom" in comp and "retfromcustomer" in comp

    records = []
    for line in text.splitlines():
        s = line.strip()
        if _skip_line(s):
            continue
        prod, tail, exp = _split_product_numbers(s)
        if not prod:
            continue
        vals = _nums(tail)
        if is_wide:
            if len(vals) < 15:
                continue
            v = vals[-15:]
            name, pack = _split_product_pack(prod)
            r = {
                "product_name": name,
                "pack": pack,
                "opening_stock": v[0],
                "opening_value": v[1],
                "purchase_stock": v[2],
                "purchase_value": v[3],
                "purchase_return": v[4],
                "total_stock": v[6],
                "sales_qty": v[7],
                "sales_value": v[8],
                "sales_return": v[9],
                "exp_damage": v[11],
                "closing_stock": v[13],
                "closing_stock_value": v[14],
            }
        else:
            if len(vals) < 11:
                continue
            v = vals[-11:]
            name, pack = _split_product_pack(prod)
            r = {
                "product_name": name,
                "pack": pack,
                "opening_stock": v[0],
                "opening_value": v[1],
                "purchase_stock": v[2],
                "purchase_value": v[3],
                "total_stock": v[4],
                "sales_qty": v[5],
                "sales_value": v[6],
                "closing_stock": v[7],
                "closing_stock_value": v[8],
            }
        if exp:
            r["expiry"] = exp
        records.append(r)
    return records
