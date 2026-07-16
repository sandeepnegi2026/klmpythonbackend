from extractors.stock_xlsx.parse_common import cell_text, is_subtotal, split_plus_qty, to_number


def parse_klm_opstk_apr_may_curstk_xls(rows):
    """KLM "Stock and Sales Statement For Company : <DIVISION>" per-division .xls (R.K. PHARMA).

    Header (single row):
        S.No | Product Name | Packing | Opstk | Pur | Apr | May | Sale | CurStk |
        StkVal | OrdQty | SalVal | Exp | Age | Rate

    Opstk=opening qty, Pur=purchase qty, Sale=current-period sales qty, CurStk=closing qty,
    StkVal=closing value, SalVal=sales value, OrdQty=order qty, Rate=unit rate. Apr/May are
    prior-month sales HISTORY (informational) and are NOT part of the current movement, so they
    are deliberately dropped. CurStk is corroborated by StkVal/Rate on every row.

    The generic `tabular` reader and the marg_opstk_curstk sibling both mis-handle this shape:
    marg_opstk_curstk treats it as its "legacy SHRI SAI" (no-PFree) variant, which NEVER binds
    closing_stock from CurStk and mis-applies a `Pur==0 -> CurStk` value fallback that corrupts
    purchase, so nearly every row fails sanity. This positional parser maps only the known
    columns by exact header text and NEVER derives a quantity from a value column.
    """
    header_idx = None
    for idx, row in enumerate(rows[:150]):
        flat = " ".join(row).lower().replace(" ", "")
        if "productname" in flat and "opstk" in flat and "apr" in flat and "may" in flat and "curstk" in flat:
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
        elif key == "sale":
            col["sale"] = i
        elif key == "curstk":
            col["curstk"] = i
        elif key == "stkval":
            col["stkval"] = i
        elif key == "salval":
            col["salval"] = i
        elif key == "ordqty":
            col["ordqty"] = i
        elif key == "rate":
            col["rate"] = i

    def at(raw_row, key):
        idx = col.get(key)
        return raw_row[idx] if idx is not None and idx < len(raw_row) else ""

    records = []
    for raw_row in rows[header_idx + 1 :]:
        if not raw_row or not cell_text(raw_row[0]).isdigit():
            continue
        product = cell_text(at(raw_row, "product"))
        if not product or is_subtotal(product) or product in {".", "0"}:
            continue

        # Opstk/Pur/Sale/CurStk may (defensively) carry a glued "n+free" token; split it so the
        # free half folds into the correct free field. Plain numeric cells split to (n, 0.0),
        # byte-identical to to_number for them.
        op, _ = split_plus_qty(at(raw_row, "opstk"))
        pur, pur_free_inline = split_plus_qty(at(raw_row, "pur"))
        sale_qty, sale_free_inline = split_plus_qty(at(raw_row, "sale"))
        close, _ = split_plus_qty(at(raw_row, "curstk"))

        rec = {
            "product_name": product,
            "pack": cell_text(at(raw_row, "pack")),
            "opening_stock": op,
            "purchase_stock": pur,
            "sales_qty": sale_qty,
            "closing_stock": close,
            "closing_stock_value": to_number(at(raw_row, "stkval")) or 0.0,
        }
        if pur_free_inline:
            rec["purchase_free"] = pur_free_inline
        if sale_free_inline:
            rec["sales_free"] = sale_free_inline
        if col.get("salval") is not None:
            rec["sales_value"] = to_number(at(raw_row, "salval")) or 0.0
        if col.get("ordqty") is not None:
            rec["order_qty"] = to_number(at(raw_row, "ordqty")) or 0.0
        if col.get("rate") is not None:
            rec["rate"] = to_number(at(raw_row, "rate")) or 0.0
        records.append(rec)

    detected = {
        "Product Name": "product_name",
        "Opstk": "opening_stock",
        "Pur": "purchase_stock",
        "Sale": "sales_qty",
        "CurStk": "closing_stock",
        "StkVal": "closing_stock_value",
    }
    return records, detected
