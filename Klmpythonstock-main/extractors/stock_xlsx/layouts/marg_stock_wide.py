from extractors.stock_xlsx.parse_common import cell_text, is_subtotal


def parse_marg_stock_wide(rows):
    header_idx = None
    for idx in range(min(len(rows) - 1, 150)):
        row_text = " ".join(rows[idx]).lower()
        next_text = " ".join(rows[idx + 1]).lower().replace(" ", "")
        if "opening" in row_text and "itemname" in next_text:
            header_idx = idx + 1
            break
    if header_idx is None:
        return [], {}
    records = []
    for raw_row in rows[header_idx + 1 :]:
        product = cell_text(raw_row[1] if len(raw_row) > 1 else "")
        if not product or is_subtotal(product) or product.startswith("*"):
            continue
        if not cell_text(raw_row[0]).isdigit():
            continue
        records.append(
            {
                "product_name": product,
                "opening_stock": raw_row[2] if len(raw_row) > 2 else "",
                "opening_value": raw_row[3] if len(raw_row) > 3 else "",
                "purchase_stock": raw_row[4] if len(raw_row) > 4 else "",
                "purchase_value": raw_row[5] if len(raw_row) > 5 else "",
                "purchase_return": raw_row[6] if len(raw_row) > 6 else "",
                "sales_qty": raw_row[8] if len(raw_row) > 8 else "",
                "sales_value": raw_row[9] if len(raw_row) > 9 else "",
                "sales_return": raw_row[10] if len(raw_row) > 10 else "",
                "closing_stock": raw_row[17] if len(raw_row) > 17 else "",
                "closing_stock_value": raw_row[18] if len(raw_row) > 18 else "",
                "pack": raw_row[19] if len(raw_row) > 19 else "",
            }
        )
    detected = {
        "ItemName": "product_name",
        "Opening Qty": "opening_stock",
        "Purchase Qty": "purchase_stock",
        "Sales Qty": "sales_qty",
        "Closing Qty": "closing_stock",
        "Closing Value": "closing_stock_value",
    }
    return records, detected
