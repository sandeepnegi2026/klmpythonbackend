"""SmartPharma360 'Stock And Sales Report' (SRI BABA MEDICAL DISTRIBUTORS, KLM).

Footer 'Powered by SmartPharma360'. One numeric row per item; every column is
printed on every row (zeros are rendered explicitly, no blank interiors and no
glyph interleaving), so a flat line/token parse is sufficient — no positional
pass needed.

Header (10 numeric movement columns + an Age column):
    Product Name | Pack | Open stock | Opening Value | Pur. Total | Pur. Value |
        Sales Total | Sale Value | sale ret total | sale ret val. |
        Closing qty | Closing Value | Age

The 11 numeric tokens after Pack are, in order:
    [0]  Open stock       opening_stock         (qty)
    [1]  Opening Value    opening_value         (rupees)
    [2]  Pur. Total       purchase_stock        (qty)
    [3]  Pur. Value       purchase_value        (rupees)
    [4]  Sales Total      sales_qty             (qty, outflow)
    [5]  Sale Value       sales_value           (rupees)
    [6]  sale ret total   sales_return          (qty, inflow)
    [7]  sale ret val.    sales_return_value    (rupees)
    [8]  Closing qty      closing_stock         (qty)
    [9]  Closing Value    closing_stock_value   (rupees)
    [10] Age              ageing in days        -> IGNORED

Reconciles per row: closing = open + purchase - sales + sales_return
(e.g. NIOCLEAN GEL 2 + 6 - 4 + 0 = 4 = Closing qty). The value columns are
rupees and must NOT land in a qty field, so this layout owns its own mapping
rather than falling through to the coarse generic/simple4 rules.

Skip the per-division 'COMNAME TOTAL' subtotal rows (8 numbers) and the final
'GRAND TOTAL' row, plus the 'Powered by SmartPharma360' footer.

Modelled on marg_ss_statement_detailed.py.
"""
from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_numbers_comma as _split_product_numbers,
    _split_product_pack,
)


def parse_smartpharma_sas(text):
    records = []
    for line in text.splitlines():
        s = line.strip()
        if _skip_line(s):
            continue
        low = s.lower()
        # Division subtotal ('COMNAME TOTAL ...') and the report 'GRAND TOTAL' row
        # both carry an 8-number tail (no sale-ret columns) and must be dropped.
        # Genuine products like 'EXTEND TOTAL TAB (KLM)' merely *contain* TOTAL and
        # are kept (they neither start with 'comname total' nor 'grand total').
        if low.startswith("comname total") or low.startswith("grand total"):
            continue
        prod, tail, exp = _split_product_numbers(s)
        if not prod:
            continue
        vals = _nums(tail)
        if len(vals) < 11:
            continue
        # Trailing 11 numbers = the 10 movement/value cells + Age.
        v = vals[-11:]
        (opening, open_val, purchase, pur_val, sales, sale_val,
         sret, sret_val, closing, clos_val) = v[:10]
        name, pack = _split_product_pack(prod)
        if not name:
            continue
        r = {
            "product_name": name,
            "pack": pack,
            "opening_stock": opening,            # Open stock
            "opening_value": open_val,           # Opening Value
            "purchase_stock": purchase,          # Pur. Total
            "purchase_value": pur_val,           # Pur. Value
            "sales_qty": sales,                  # Sales Total (outflow)
            "sales_value": sale_val,             # Sale Value
            "sales_return": sret,                # sale ret total (inflow)
            "sales_return_value": sret_val,      # sale ret val.
            "closing_stock": closing,            # Closing qty
            "closing_stock_value": clos_val,     # Closing Value
        }
        if exp:
            r["expiry"] = exp
        records.append(r)
    return records
