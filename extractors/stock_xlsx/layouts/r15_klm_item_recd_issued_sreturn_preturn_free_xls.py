from extractors.stock_xlsx.parse_common import cell_text, is_subtotal, to_number


def parse_klm_item_recd_issued_sreturn_preturn_free_xls(rows):
    """KLM-division "STOCK AND SALES STATEMENT" .xls with the header run
    (spaces-stripped, lowercased)::

        itemnamepackopeningreceivedissuedvalueclosingsreturnpreturnfree

    Emitted by the SRI LAKSHMI ANNAPURNA MEDICAL AGENCIES export ("klm derma new.xls").
    The single header row reads (exact cell text)::

        Item Name | Pack | Opening | Received | Issued | Value | Closing | SReturn | PReturn | free

    Layout quirks that break the generic `tabular` reader:
      * The header label "Item Name" sits in column 2, but the PRODUCT NAME in every
        data row is written in column 0 (cols 1-2 are blank). The generic tabular
        aligner keys the product off the header column, finds it empty in the data
        rows, and drops all 29 product rows -- capturing only the "GroupTotal :" footer.
      * The movement columns Pack..PReturn (data cols 3-10) DO line up with the header.
      * The `free` value does NOT land under its header column (11); the real free
        quantity is written in the LAST populated cell of the row (col 14). Col 11 is a
        spurious duplicate that is always "0".

    Canonical mapping (mapped by EXACT header text, product taken positionally from col 0):
        Opening  -> opening_stock       (opening qty)
        Received -> purchase_stock      (received/purchase qty, inflow +)
        Issued   -> sales_qty           (issued/sale qty, outflow -)
        Value    -> sales_value         (RUPEE value of the issue -- value only, never a qty)
        Closing  -> closing_stock       (closing qty)
        SReturn  -> sales_return        (sales return qty, inflow +)
        PReturn  -> purchase_return     (purchase return qty, outflow -)
        free     -> sales_free          (free goods ISSUED, outflow -)  [col 14]

    The `free` column is a SALES free (free goods given away on issue), i.e. an OUTFLOW.
    Verified: opening + purchase + sales_return - issued(sales_qty) - purchase_return
              - sales_free = closing holds on 29/29 rows. Treating free as a purchase
    (inflow) free instead fails the 3 rows that carry free stock.

    NEVER derives a quantity from the Value column (it stays sales_value only).
    """
    header_idx = None
    for idx, row in enumerate(rows[:80]):
        flat = " ".join(cell_text(c) for c in row).lower().replace(" ", "")
        if (
            "itemname" in flat and "opening" in flat and "received" in flat
            and "issued" in flat and "closing" in flat and "sreturn" in flat
            and "preturn" in flat and flat.rstrip().endswith("free")
        ):
            header_idx = idx
            break
    if header_idx is None:
        return [], {}

    hdr = rows[header_idx]
    col = {}
    for i, cell in enumerate(hdr):
        key = cell_text(cell).lower().replace(" ", "")
        if key == "pack":
            col["pack"] = i
        elif key == "opening":
            col["opening"] = i
        elif key == "received":
            col["received"] = i
        elif key == "issued":
            col["issued"] = i
        elif key == "value":
            col["value"] = i
        elif key == "closing":
            col["closing"] = i
        elif key == "sreturn":
            col["sreturn"] = i
        elif key == "preturn":
            col["preturn"] = i

    for req in ("opening", "received", "issued", "closing"):
        if req not in col:
            return [], {}

    def cell_at(raw_row, key):
        idx = col.get(key)
        if idx is None or idx >= len(raw_row):
            return ""
        return cell_text(raw_row[idx])

    def num(raw_row, key):
        idx = col.get(key)
        if idx is None or idx >= len(raw_row):
            return 0.0
        return to_number(raw_row[idx]) or 0.0

    def free_qty(raw_row):
        # The `free` quantity is the LAST populated cell of the row (data col 14),
        # NOT the spurious "0" under the header's free column (11).
        last_free_col = col.get("preturn", -1)
        for i in range(len(raw_row) - 1, last_free_col, -1):
            txt = cell_text(raw_row[i])
            if txt != "":
                return to_number(txt) or 0.0
        return 0.0

    records = []
    for raw_row in rows[header_idx + 1 :]:
        if not raw_row:
            continue
        product = cell_text(raw_row[0])
        if not product:
            continue
        low = product.lower()
        # Skip the division band ("KLM DERMA -SM") and the "GroupTotal :" footer:
        # bands/footers carry no per-item movement in the aligned Opening/Closing cols.
        if is_subtotal(product) or low.startswith("grouptotal") or low.startswith("group total"):
            continue
        opening = num(raw_row, "opening")
        received = num(raw_row, "received")
        issued = num(raw_row, "issued")
        closing = num(raw_row, "closing")
        # A division band row ("KLM DERMA -SM") is a short row with all-empty movement
        # cells (the loader trims trailing empties) -> skip.
        if (
            cell_at(raw_row, "opening") == ""
            and cell_at(raw_row, "received") == ""
            and cell_at(raw_row, "closing") == ""
        ):
            continue

        rec = {
            "product_name": product,
            "pack": cell_text(raw_row[col["pack"]]) if "pack" in col and col["pack"] < len(raw_row) else "",
            "opening_stock": opening,
            "purchase_stock": received,
            "sales_qty": issued,
            "sales_free": free_qty(raw_row),
            "sales_return": num(raw_row, "sreturn"),
            "purchase_return": num(raw_row, "preturn"),
            "closing_stock": closing,
            "sales_value": num(raw_row, "value"),
        }
        records.append(rec)

    detected = {
        "Item Name": "product_name",
        "Opening": "opening_stock",
        "Received": "purchase_stock",
        "Issued": "sales_qty",
        "Value": "sales_value",
        "Closing": "closing_stock",
        "SReturn": "sales_return",
        "PReturn": "purchase_return",
        "free": "sales_free",
    }
    return records, detected
