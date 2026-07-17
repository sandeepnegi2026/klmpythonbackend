from extractors.stock_xlsx.parse_common import cell_text, is_subtotal, to_number


def detect(rows):
    """Gate: KLM "Stock and Sales Statement" FULL-movement per-division .xls with the
    Apr|May prior-month pair and NO SRetun column (RATHNA AGENCIES). See parse fn docstring.
    """
    flat = " ".join(" ".join(cell_text(c) for c in row) for row in rows[:12]).lower().replace(" ", "")
    return (
        "productname" in flat
        and "pfreepurret" in flat          # contiguous PFree|PurRet run (full-movement export)
        and "aprmay" in flat               # prior-month pair Apr|May (this family, not Mar|Apr)
        and "sfree" in flat
        and "curstk" in flat
        and "sretun" not in flat           # SRetun-bearing variant -> the pfree_purret_marapr sibling
        and "sreturn" not in flat
    )


def parse_klm_ss_pfree_purret_aprmay_sfree_adj_curstk_xls(rows):
    """KLM "Stock and Sales Statement For Company : <DIVISION>" FULL-movement per-division .xls
    (RATHNA AGENCIES; e.g. "KLM- COSMO"). One book per division.

    Single header row (16 columns), exact text::

        S.No | Product Name | Packing | Opstk | Pur | PFree | PurRet | Apr | May | Sale |
        SFree | Adj+/- | CurStk | StkVal | SalVal | Rate

    Movement -> canonical mapping (mapped by EXACT header text, positionally):
        Opstk  -> opening_stock            (opening qty)
        Pur    -> purchase_stock           (purchase qty, inflow +)
        PFree  -> purchase_free            (free-on-purchase qty, inflow +)
        PurRet -> purchase_return          (purchase return qty, outflow -)
        Sale   -> sales_qty                (current-period sale qty, outflow -)
        SFree  -> sales_free               (free-on-sale qty, outflow -)
        Adj+/- -> signed adjustment folded into sales_return (+) / sales_free (-)
        CurStk -> closing_stock            (closing qty)
        StkVal -> closing_stock_value      (closing rupee value)
        SalVal -> sales_value              (sales rupee value)
        Rate   -> rate

    The two columns "Apr" and "May" are PRIOR-MONTH sales HISTORY (informational) and are
    deliberately dropped -- they are NOT part of the current movement. With that,
    closing = opening + purchase + purchase_free - purchase_return
              - sales_qty - sales_free + sales_return  holds on every row (verified 33/33 rows
    of KLM COSMO).

    This distinguishes it from two existing siblings, both of whose header searches never bind
    on this export:
      * klm_opstk_apr_may_curstk_xls -- expects the Apr|May pair but has NO PFree/PurRet/SFree/
        Adj columns, so it silently DROPS all four movement columns and 55% of rows fail sanity.
      * r15_klm_ss_pfree_purret_marapr_curstk_xls (SENTHIL PHARMA) -- requires a SRetun column
        and the Mar|Apr prior-month pair, both absent here.

    NEVER derives a quantity from a value column (StkVal/SalVal stay value-only).
    """
    header_idx = None
    for idx, row in enumerate(rows[:150]):
        flat = " ".join(cell_text(c) for c in row).lower().replace(" ", "")
        if (
            "productname" in flat and "opstk" in flat and "pfree" in flat
            and "purret" in flat and "sfree" in flat and "curstk" in flat
            and "apr" in flat and "may" in flat
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
        elif key in {"adj+/-", "adj"}:
            col["adj"] = i
        elif key == "curstk":
            col["curstk"] = i
        elif key == "stkval":
            col["stkval"] = i
        elif key == "salval":
            col["salval"] = i
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
            "closing_stock": num(raw_row, "curstk"),
            "closing_stock_value": num(raw_row, "stkval"),
        }
        # Signed Adj+/-: adds to closing when +, subtracts when -. Fold into the +sales_return
        # slot for positive and the -sales_free slot for negative so the equation stays exact.
        adj = num(raw_row, "adj")
        if adj > 0:
            rec["sales_return"] = adj
        elif adj < 0:
            rec["sales_free"] = rec["sales_free"] + (-adj)

        if "salval" in col:
            rec["sales_value"] = num(raw_row, "salval")
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
        "CurStk": "closing_stock",
        "StkVal": "closing_stock_value",
    }
    return records, detected
