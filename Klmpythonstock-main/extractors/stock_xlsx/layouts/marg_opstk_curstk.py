from extractors.stock_xlsx.parse_common import cell_text, is_subtotal, split_plus_qty, to_number


def parse_marg_opstk_curstk(rows):
    header_idx = None
    for idx, row in enumerate(rows[:150]):
        flat = " ".join(row).lower()
        if "product name" in flat and "opstk" in flat.replace(" ", ""):
            header_idx = idx
            break
    if header_idx is None:
        return [], {}
    col = {}
    for i, cell in enumerate(rows[header_idx]):
        key = cell_text(cell).lower().replace(" ", "")
        if key in {"productname", "itemname"}:
            col["product"] = i
        elif key == "packing":
            col["pack"] = i
        elif key == "opstk":
            col["opstk"] = i
        elif key == "pur":
            col["pur"] = i
        elif key == "pfree":
            col["pfree"] = i
        elif key == "sale":
            col["sale"] = i
        elif key == "curstk":
            col["curstk"] = i
        elif key == "stkval":
            col["stkval"] = i

    def at(raw_row, key):
        idx = col.get(key)
        return raw_row[idx] if idx is not None and idx < len(raw_row) else ""

    records = []
    for raw_row in rows[header_idx + 1 :]:
        product = cell_text(at(raw_row, "product"))
        if not product or is_subtotal(product) or product in {".", "0"}:
            continue
        if not cell_text(raw_row[0]).isdigit():
            continue
        op, _ = split_plus_qty(at(raw_row, "opstk"))
        pur, pur_free = split_plus_qty(at(raw_row, "pur"))
        if pur == 0 and col.get("curstk") is not None:
            pur, pur_free = split_plus_qty(at(raw_row, "curstk"))
        records.append(
            {
                "product_name": product,
                "pack": cell_text(at(raw_row, "pack")),
                "opening_stock": op,
                "purchase_stock": pur,
                "purchase_free": pur_free,
                "sales_qty": to_number(at(raw_row, "sale")) or 0.0,
                "closing_stock_value": to_number(at(raw_row, "stkval")),
            }
        )
    detected = {
        "Product Name": "product_name",
        "Opstk": "opening_stock",
        "Pur": "purchase_stock",
        "Sale": "sales_qty",
        "CurStk": "closing_stock",
    }
    return records, detected
