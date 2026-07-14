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
        elif key == "purret":
            col["purret"] = i
        elif key == "sale":
            col["sale"] = i
        elif key == "sfree":
            col["sfree"] = i
        elif key.startswith("adj"):
            col["adj"] = i
        elif key == "curstk":
            col["curstk"] = i
        elif key == "stkval":
            col["stkval"] = i
        elif key == "salval":
            col["salval"] = i

    def at(raw_row, key):
        idx = col.get(key)
        return raw_row[idx] if idx is not None and idx < len(raw_row) else ""

    # The RATHNA rich shape breaks out PFree/PurRet/SFree/Adj and a real CurStk closing
    # column; the legacy SHRI SAI shape has only OpStk/Pur/Sale/CurStk/StkVal (NO PFree) and
    # prints its value in CurStk when Pur is blank. PFree presence is the sole discriminator
    # (SHRI SAI also carries StkVal, so keying on StkVal would wrongly reclassify it and
    # disable the pur==0->CurStk fallback it needs). Gate the rich binding on PFree only.
    rich = col.get("pfree") is not None

    records = []
    for raw_row in rows[header_idx + 1 :]:
        product = cell_text(at(raw_row, "product"))
        if not product or is_subtotal(product) or product in {".", "0"}:
            continue
        if not cell_text(raw_row[0]).isdigit():
            continue
        op, _ = split_plus_qty(at(raw_row, "opstk"))
        pur, pur_free_inline = split_plus_qty(at(raw_row, "pur"))
        if not rich and pur == 0 and col.get("curstk") is not None:
            pur, pur_free_inline = split_plus_qty(at(raw_row, "curstk"))

        rec = {
            "product_name": product,
            "pack": cell_text(at(raw_row, "pack")),
            "opening_stock": op,
            "purchase_stock": pur,
            "sales_qty": to_number(at(raw_row, "sale")) or 0.0,
            "closing_stock_value": to_number(at(raw_row, "stkval")),
        }
        if rich:
            close, _ = split_plus_qty(at(raw_row, "curstk"))
            rec["closing_stock"] = close
            rec["purchase_free"] = to_number(at(raw_row, "pfree")) or 0.0
            rec["sales_free"] = to_number(at(raw_row, "sfree")) or 0.0
            rec["purchase_return"] = to_number(at(raw_row, "purret")) or 0.0
            if col.get("salval") is not None:
                rec["sales_value"] = to_number(at(raw_row, "salval")) or 0.0
            adj = to_number(at(raw_row, "adj")) or 0.0
            if adj:
                rec.setdefault("extra_data", {})["adjustment"] = adj
        else:
            rec["purchase_free"] = pur_free_inline
        records.append(rec)
    detected = {
        "Product Name": "product_name",
        "Opstk": "opening_stock",
        "Pur": "purchase_stock",
        "Sale": "sales_qty",
        "CurStk": "closing_stock",
    }
    return records, detected
