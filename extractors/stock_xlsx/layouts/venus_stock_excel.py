import re

from extractors.stock_xlsx.parse_common import cell_text, is_subtotal


# Header token (lower, spaces AND dots removed) -> canonical field. The KLM Venus export
# prints DOTTED headers "P.Qty"/"S.Qty"/"S.Val"; the old code stripped only spaces, so
# "p.qty" != "pqty" and purchase/sales/sales-value came out EMPTY (every movement row then
# failed the identity). Stripping dots too binds them. The scheme/return/adjustment columns
# (P.Sch/S.Sch/CrQty/DbQty/StkAd) are added with their reconciliation-verified signs so the
# identity op + P.Qty + P.Sch - S.Qty - S.Sch + StkAd == ClStk holds (AAGAM 71/71 rows).
_VENUS_COLS = {
    "item": "product_name", "itemname": "product_name",
    "opstk": "opening_stock",
    "pqty": "purchase_stock", "psch": "purchase_free",
    "sqty": "sales_qty", "ssch": "sales_free", "sval": "sales_value",
    "crqty": "sales_return",        # credit note (goods back in, +sr)
    "dbqty": "purchase_return",     # debit note (goods to supplier, -pr)
    "stkad": "shortage",            # signed stock adjustment (triage's adjusted base +shortage)
    "clstk": "closing_stock", "clval": "closing_stock_value",
}
_VENUS_DISPLAY = {
    "product_name": "Item", "opening_stock": "OpStk", "purchase_stock": "P.Qty",
    "purchase_free": "P.Sch", "sales_qty": "S.Qty", "sales_free": "S.Sch",
    "sales_value": "S.Val", "sales_return": "CrQty", "purchase_return": "DbQty",
    "shortage": "StkAd", "closing_stock": "ClStk", "closing_stock_value": "ClVal",
}


def parse_venus_stock_excel(rows):
    header_idx = None
    col = {}
    for idx, row in enumerate(rows[:150]):
        for j, cell in enumerate(row):
            key = cell_text(cell).lower().replace(" ", "").replace(".", "")
            canon = _VENUS_COLS.get(key)
            # First occurrence wins: StkAd repeats across two adjacent columns holding the
            # same value; binding once avoids double-counting the adjustment.
            if canon and canon not in col:
                col[canon] = j
        if "opening_stock" in col and "product_name" in col:
            header_idx = idx
            break
    if header_idx is None:
        return [], {}
    item_col = col["product_name"]
    records = []
    for raw_row in rows[header_idx + 1 :]:
        product = cell_text(raw_row[item_col] if item_col < len(raw_row) else "")
        if not product or is_subtotal(product):
            continue
        if product.startswith("KLM ") or re.match(r"^XA\d+$", product, re.I):
            continue
        if len(product) < 4:
            continue
        record = {"product_name": product}
        for canon, j in col.items():
            if canon == "product_name":
                continue
            record[canon] = raw_row[j] if j < len(raw_row) else ""
        records.append(record)
    detected = {_VENUS_DISPLAY[canon]: canon for canon in col}
    return records, detected
