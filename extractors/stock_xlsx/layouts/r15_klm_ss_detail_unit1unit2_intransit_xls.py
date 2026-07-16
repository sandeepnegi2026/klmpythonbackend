from extractors.stock_xlsx.parse_common import cell_text, is_subtotal, to_number


def parse_klm_ss_detail_unit1unit2_intransit_xls(rows):
    """KLM "Sales And Stock (Detail)" wide .xlsx export (JEEVAN DEEP PHARMA).

    One book; a single 22-column header row, exact text::

        NameToDisplay | Marketing Group | OpStock(Unit1) | OpValue |
        PurchaseQty(Unit1) | In Stock(Unit1) | PurchaseValue | SalesQty(Unit1) |
        Out Stock(Unit1) | SalesValue | Cur.Stock(Unit1) | Cl.Stock As On(Unit1) |
        Cl.Value | In Stock Value | OpStock(Unit2) | SalesReturnQty |
        SurplusStock(Unit1) | PurchaseReturnQty | ShortageStock(Unit1) |
        IssueLocationTransfer(Unit1) | Out Stock Value | In Transit(Unit1)

    The generic `tabular` fallback (core.header_match) mangles this sheet: it binds
    OpStock(Unit1) -> pack, OpValue -> sales_value, PurchaseValue -> purchase_stock
    (a VALUE stolen into a QTY slot!), SalesValue -> sales_qty, and leaves every real
    quantity column (PurchaseQty/SalesQty/Cl.Stock As On/Cur.Stock/SalesReturnQty/
    PurchaseReturnQty) unbound -> 100% SANITY_FAILED.  This parser binds every column by
    EXACT normalized header text, positionally, keeping qty and value strictly separate.

    Movement -> canonical mapping (all by exact header text):
        OpStock(Unit1)        -> opening_stock        (opening qty, Unit1)
        PurchaseQty(Unit1)    -> purchase_stock       (purchase qty, inflow +)
        SalesQty(Unit1)       -> sales_qty            (sale qty, outflow -)
        SalesReturnQty        -> sales_return         (sales return qty, inflow +)
        PurchaseReturnQty     -> purchase_return      (purchase return qty, outflow -)
        Cl.Stock As On(Unit1) -> closing_stock        (closing qty)
        OpValue               -> opening_value
        PurchaseValue         -> purchase_value
        SalesValue            -> sales_value
        Cl.Value              -> closing_stock_value

    With that: opening + purchase + sales_return - purchase_return - sales_qty = closing
    holds on 266/267 product rows (99.6%).  The 22-column extras are intentionally NOT
    folded into the identity:
      - OpStock(Unit2)/In Stock/Out Stock/Cur.Stock/In Stock Value/Out Stock Value are
        alternate-unit and derived running totals (redundant with the above).
      - SurplusStock/ShortageStock/IssueLocationTransfer/In Transit are ERP adjustment
        buckets the vendor does NOT feed cleanly into closing (e.g. KLM-D3 60K prints
        surplus 6 with closing 0; ESSFOL surplus 1 == shortage 1 cancel), so folding them
        BREAKS more rows than it fixes -- verified: base identity 266/267 vs surplus/
        shortage variants 264-265/267.  They are left out to keep the equation exact.
      The lone residual (KOXITUF: opening 17, closing 0, shortage 17) is a real vendor-side
      write-off in the SOURCE numbers, not a parse error.

    NEVER derives a quantity from a value column (OpValue/PurchaseValue/SalesValue/Cl.Value
    stay value-only).

    Gate token (flat, lowercased, spaces stripped): a contiguous header run unique to this
    KLM export -- "nametodisplaymarketinggroupopstock(unit1)" -- present in no other file.
    """
    header_idx = None
    for idx, row in enumerate(rows[:150]):
        flat = " ".join(cell_text(c) for c in row).lower().replace(" ", "")
        if (
            "nametodisplay" in flat and "marketinggroup" in flat
            and "opstock(unit1)" in flat and "cl.stockason(unit1)" in flat
            and "issuelocationtransfer(unit1)" in flat
        ):
            header_idx = idx
            break
    if header_idx is None:
        return [], {}

    col = {}
    for i, cell in enumerate(rows[header_idx]):
        key = cell_text(cell).lower().replace(" ", "")
        if key in {"nametodisplay", "itemname", "productname"}:
            col["product"] = i
        elif key in {"marketinggroup"}:
            col["group"] = i
        elif key == "opstock(unit1)":
            col["opstk"] = i
        elif key == "opvalue":
            col["opval"] = i
        elif key == "purchaseqty(unit1)":
            col["pur"] = i
        elif key == "purchasevalue":
            col["purval"] = i
        elif key == "salesqty(unit1)":
            col["sale"] = i
        elif key == "salesvalue":
            col["saleval"] = i
        elif key == "salesreturnqty":
            col["sret"] = i
        elif key == "purchasereturnqty":
            col["pret"] = i
        elif key == "cl.stockason(unit1)":
            col["closing"] = i
        elif key == "cl.value":
            col["clval"] = i

    # Require the core movement columns; if any are missing the header didn't line up.
    for req in ("product", "opstk", "pur", "sale", "closing"):
        if req not in col:
            return [], {}

    def num(raw_row, key):
        idx = col.get(key)
        if idx is None or idx >= len(raw_row):
            return 0.0
        return to_number(raw_row[idx]) or 0.0

    records = []
    for raw_row in rows[header_idx + 1 :]:
        if not raw_row:
            continue
        product = cell_text(raw_row[col["product"]]) if col["product"] < len(raw_row) else ""
        if not product or is_subtotal(product):
            continue
        pl = product.lower().strip()
        # Footer / non-product rows.
        if pl.startswith("grand total") or pl.startswith("total") or pl.startswith("company"):
            continue
        if not any(ch.isalnum() for ch in pl):
            continue

        rec = {
            "product_name": product,
            "opening_stock": num(raw_row, "opstk"),
            "purchase_stock": num(raw_row, "pur"),
            "sales_qty": num(raw_row, "sale"),
            "sales_return": num(raw_row, "sret"),
            "purchase_return": num(raw_row, "pret"),
            "closing_stock": num(raw_row, "closing"),
            "opening_value": num(raw_row, "opval"),
            "purchase_value": num(raw_row, "purval"),
            "sales_value": num(raw_row, "saleval"),
            "closing_stock_value": num(raw_row, "clval"),
        }
        if "group" in col and col["group"] < len(raw_row):
            rec["vendor_gstin"] = cell_text(raw_row[col["group"]])
        records.append(rec)

    detected = {
        "NameToDisplay": "product_name",
        "OpStock(Unit1)": "opening_stock",
        "PurchaseQty(Unit1)": "purchase_stock",
        "SalesQty(Unit1)": "sales_qty",
        "SalesReturnQty": "sales_return",
        "PurchaseReturnQty": "purchase_return",
        "Cl.Stock As On(Unit1)": "closing_stock",
        "OpValue": "opening_value",
        "PurchaseValue": "purchase_value",
        "SalesValue": "sales_value",
        "Cl.Value": "closing_stock_value",
    }
    return records, detected
