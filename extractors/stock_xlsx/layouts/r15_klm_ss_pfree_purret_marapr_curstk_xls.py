from extractors.stock_xlsx.parse_common import cell_text, is_subtotal, to_number


def parse_klm_ss_pfree_purret_marapr_curstk_xls(rows):
    """KLM "Stock and Sales Statement For Company : <DIVISION>" FULL-movement per-division .xls
    (SENTHIL PHARMA). One book per division (COSMO Q / DERMA / DERMACOR / PEDIA ...).

    Single header row (22 columns), exact text::

        S.No | Product Name | Packing | Opstk | Pur | PFree | PurRet | Mar | Apr | Sale |
        SFree | SRetun | Adj+/- | CurStk | StkVal | OrdQty | OrdFree | SalVal | Exp | Age |
        Rate | Last PDate

    Movement -> canonical mapping (mapped by EXACT header text, positionally):
        Opstk  -> opening_stock            (opening qty)
        Pur    -> purchase_stock           (purchase qty, inflow +)
        PFree  -> purchase_free            (free-on-purchase qty, inflow +)
        PurRet -> purchase_return          (purchase return qty, outflow -)
        Sale   -> sales_qty                (current-period sale qty, outflow -)
        SFree  -> sales_free               (free-on-sale qty, outflow -)
        SRetun -> sales_return             (sales return qty, inflow +)
        Adj+/- -> signed adjustment folded into sales_return (+) / sales_free (-)
        CurStk -> closing_stock            (closing qty)
        StkVal -> closing_stock_value      (closing rupee value)
        SalVal -> sales_value              (sales rupee value)
        OrdQty -> order_qty ; Rate -> rate

    The two columns "Mar" and "Apr" are PRIOR-MONTH sales HISTORY (informational) and are
    deliberately dropped -- they are NOT part of the current movement. With that,
    closing = opening + purchase + purchase_free - purchase_return
              - sales_qty - sales_free + sales_return  holds on every row (verified 100%
    across all 4 SENTHIL PHARMA books).

    This is the richer sibling of klm_opstk_apr_may_curstk_xls: that layout expects the
    prior-month columns "Apr|May" between Pur and Sale and has NO PFree/PurRet/SFree/SRetun/
    Adj columns, so its header search never binds and it extracts 0 rows on this export.

    NEVER derives a quantity from a value column (StkVal/SalVal stay value-only).
    """
    header_idx = None
    for idx, row in enumerate(rows[:150]):
        flat = " ".join(cell_text(c) for c in row).lower().replace(" ", "")
        if (
            "productname" in flat and "opstk" in flat and "pfree" in flat
            and "purret" in flat and "sfree" in flat and "sretun" in flat
            and "curstk" in flat
        ):
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
        elif key in {"sretun", "sreturn"}:
            col["sretun"] = i
        elif key in {"adj+/-", "adj"}:
            col["adj"] = i
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

    # Require the core movement columns; if any are missing the header didn't line up.
    for req in ("product", "opstk", "pur", "curstk"):
        if req not in col:
            return [], {}

    def num(raw_row, key):
        idx = col.get(key)
        if idx is None or idx >= len(raw_row):
            return 0.0
        return to_number(raw_row[idx]) or 0.0

    records = []
    for raw_row in rows[header_idx + 1 :]:
        if not raw_row or not cell_text(raw_row[0]).isdigit():
            continue
        product = cell_text(raw_row[col["product"]]) if col["product"] < len(raw_row) else ""
        if not product or is_subtotal(product) or product in {".", "0"}:
            continue

        rec = {
            "product_name": product,
            "pack": cell_text(raw_row[col["pack"]]) if "pack" in col and col["pack"] < len(raw_row) else "",
            "opening_stock": num(raw_row, "opstk"),
            "purchase_stock": num(raw_row, "pur"),
            "purchase_free": num(raw_row, "pfree"),
            "purchase_return": num(raw_row, "purret"),
            "sales_qty": num(raw_row, "sale"),
            "sales_free": num(raw_row, "sfree"),
            "sales_return": num(raw_row, "sretun"),
            "closing_stock": num(raw_row, "curstk"),
            "closing_stock_value": num(raw_row, "stkval"),
        }
        # Signed Adj+/-: adds to closing when +, subtracts when -. Fold into the +sales_return
        # slot for positive and the -sales_free slot for negative so the equation stays exact.
        adj = num(raw_row, "adj")
        if adj > 0:
            rec["sales_return"] = rec["sales_return"] + adj
        elif adj < 0:
            rec["sales_free"] = rec["sales_free"] + (-adj)

        if "salval" in col:
            rec["sales_value"] = num(raw_row, "salval")
        if "ordqty" in col:
            rec["order_qty"] = num(raw_row, "ordqty")
        if "rate" in col:
            rec["rate"] = num(raw_row, "rate")
        records.append(rec)

    detected = {
        "Product Name": "product_name",
        "Opstk": "opening_stock",
        "Pur": "purchase_stock",
        "PFree": "purchase_free",
        "PurRet": "purchase_return",
        "Sale": "sales_qty",
        "SFree": "sales_free",
        "SRetun": "sales_return",
        "CurStk": "closing_stock",
        "StkVal": "closing_stock_value",
    }
    return records, detected
