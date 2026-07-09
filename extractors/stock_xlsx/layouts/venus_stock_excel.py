import re

from extractors.stock_xlsx.parse_common import cell_text, is_subtotal


def parse_venus_stock_excel(rows):
    header_idx = None
    col = {}
    for idx, row in enumerate(rows[:150]):
        for j, cell in enumerate(row):
            key = cell_text(cell).lower().replace(" ", "")
            # Some Venus-shaped exports label the product column "Item Name"
            # (-> "itemname") instead of bare "Item"; treat it as the item col.
            if key == "itemname":
                key = "item"
            if key in {"item", "opstk", "pqty", "sqty", "sval", "clstk", "clval"}:
                col[key] = j
        if "opstk" in col and "item" in col:
            header_idx = idx
            break
    if header_idx is None:
        return [], {}
    item_col = col.get("item", 6)
    records = []
    for raw_row in rows[header_idx + 1 :]:
        product = cell_text(raw_row[item_col] if item_col < len(raw_row) else "")
        if not product or is_subtotal(product):
            continue
        if product.startswith("KLM ") or re.match(r"^XA\d+$", product, re.I):
            continue
        if len(product) < 4:
            continue
        records.append(
            {
                "product_name": product,
                "opening_stock": raw_row[col["opstk"]]
                if col.get("opstk") is not None and col["opstk"] < len(raw_row)
                else "",
                "purchase_stock": raw_row[col["pqty"]]
                if col.get("pqty") is not None and col["pqty"] < len(raw_row)
                else "",
                "sales_qty": raw_row[col["sqty"]]
                if col.get("sqty") is not None and col["sqty"] < len(raw_row)
                else "",
                "sales_value": raw_row[col["sval"]]
                if col.get("sval") is not None and col["sval"] < len(raw_row)
                else "",
                "closing_stock": raw_row[col["clstk"]]
                if col.get("clstk") is not None and col["clstk"] < len(raw_row)
                else "",
                "closing_stock_value": raw_row[col["clval"]]
                if col.get("clval") is not None and col["clval"] < len(raw_row)
                else "",
            }
        )
    detected = {
        "Item": "product_name",
        "OpStk": "opening_stock",
        "P.Qty": "purchase_stock",
        "S.Qty": "sales_qty",
        "S.Val": "sales_value",
        "ClStk": "closing_stock",
        "ClVal": "closing_stock_value",
    }
    return records, detected
