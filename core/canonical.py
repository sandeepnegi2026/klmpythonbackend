DIVISIONS = [
    "COSMOCOR",
    "DERMACOR",
    "COSMOQ",
    "COSMO",
    "PHARMA",
    "DERMA",
    "PEDIA",
]

PARTY_FIELDS = {
    "vendor_name": {"scope": "header", "type": "str", "required": True, "synonyms": ["vendor", "firm", "agency"]},
    "division": {"scope": "header", "type": "enum", "required": True, "synonyms": ["company", "division", "brand", "cosmo", "pharma", "derma", "cosmoq", "pedia", "cosmocor", "dermacor"]},
    "party_name": {"scope": "party", "type": "str", "required": True, "synonyms": ["customer", "party", "buyer", "shop", "store", "party name", "customer name", "ledger account", "ledger"]},
    "party_location": {"scope": "party", "type": "str", "required": False, "synonyms": ["location", "city", "town", "address", "address1", "address2", "place", "area", "zone", "route", "territory", "station"]},
    "party_gstin": {"scope": "party", "type": "str", "required": False, "synonyms": ["gstin", "gst no", "tin"]},
    "hsn_code": {"scope": "line_item", "type": "str", "required": False, "synonyms": ["hsn", "hsn code", "code", "product code"]},
    "invoice_number": {"scope": "line_item", "type": "str", "required": True, "synonyms": ["invno", "inv no", "invoice", "invoice no", "bill no", "bill", "srno", "bill ref", "doc no", "docno", "feedno", "feed no", "vch no", "voucher no", "voucher"]},
    "invoice_date": {"scope": "line_item", "type": "date", "required": True, "synonyms": ["date", "bill date", "inv date", "invoice date", "billdate"]},
    "product_name": {"scope": "line_item", "type": "str", "required": True, "synonyms": ["item", "itemname", "item name", "description", "product", "product name", "particulars", "medicinename", "medicine name", "d e s c r i p t i o n"]},
    "pack": {"scope": "line_item", "type": "str", "required": False, "synonyms": ["pack", "size", "uom", "packing", "unit"]},
    "batch_no": {"scope": "line_item", "type": "str", "required": False, "synonyms": ["batch", "batch no", "lot"]},
    "expiry": {"scope": "line_item", "type": "str", "required": False, "synonyms": ["exp", "expdt", "exp date", "expiry"]},
    "mrp": {"scope": "line_item", "type": "num", "required": False, "synonyms": ["mrp", "max retail price", "m r p"]},
    "qty": {"scope": "line_item", "type": "num", "required": True, "synonyms": ["qty", "quantity", "qnty", "sale qty", "s qty"]},
    # "scch qty" / "n scch qty" — KLM DB-style dump exports (SWETA AGENCY "n_scch_qty")
    # carry the scheme/free quantity in a column literally headed n_scch_qty. The full
    # "n scch qty" form is required for an EXACT (1.0) match: a bare "scch qty" candidate
    # only reaches the contains score (0.88), which TIES with qty's own "qty"-substring hit
    # on that header and loses the tie (strict >, qty is the earlier field), leaving the
    # column unmapped. "scch" appears in no other header corpus-wide (113-header cache sweep
    # + 67-file party_xlsx regression re-sim: zero other mappings change).
    "free_qty": {"scope": "line_item", "type": "num", "required": False, "synonyms": ["free", "scheme qty", "sch qty", "free qty", "freeqty", "s qty", "fqty", "scch qty", "n scch qty", "schm", "schm."]},
    "rate": {"scope": "line_item", "type": "num", "required": True, "synonyms": ["rate", "price", "mrp rate"]},
    "sales_rate": {"scope": "line_item", "type": "num", "required": False, "synonyms": ["s rate", "sale rate", "selling rate", "sales rate"]},
    "purchase_rate": {"scope": "line_item", "type": "num", "required": False, "synonyms": ["purchase rate", "pur rate", "p rate"]},
    "ptr": {"scope": "line_item", "type": "num", "required": False, "synonyms": ["ptr"]},
    "claim_qty": {"scope": "line_item", "type": "num", "required": False, "synonyms": ["claim qty", "claim quantity", "clm qty", "clmqty"]},
    "claim_value": {"scope": "line_item", "type": "num", "required": False, "synonyms": ["claim value", "claim amount", "clm val", "clm amt"]},
    "taxable_value": {"scope": "line_item", "type": "num", "required": True, "synonyms": ["taxable value", "taxable amt", "taxable amount", "taxeble value"]},
    "gst_rate": {"scope": "line_item", "type": "num", "required": False, "synonyms": ["gst%", "gst rate", "tax%", "%"]},
    "gst_amount": {"scope": "line_item", "type": "num", "required": False, "synonyms": ["gst", "gst amount", "tax", "taxamt", "tax amount", "gstamt", "gst amt"]},
    "discount_amount": {"scope": "line_item", "type": "num", "required": False, "synonyms": ["s disc", "disc", "discount", "scheme disc", "sch disc", "prod dis", "prod.dis", "sch amt", "scheme amt", "scheme amount", "cash disc", "cashdisc", "cd amt", "scm disc", "scmdisc", "td amt", "tdamt"]},
    "discount_percent": {"scope": "line_item", "type": "num", "required": False, "synonyms": ["discount percent", "disc pct", "disc %", "sch per", "schper", "scheme per", "scheme percent", "cd%", "cd %", "disc per", "discper", "b dis%"]},
    "net_amount": {"scope": "line_item", "type": "num", "required": False, "synonyms": ["net amount", "net amt"]},
    "amount": {"scope": "line_item", "type": "num", "required": False, "synonyms": ["amount", "value", "total", "sale amount", "grs amt", "gross amt", "gross amount"]},
    "report_type_label": {"scope": "header", "type": "str", "required": False, "synonyms": ["report type", "report for", "statement type", "title"]},
}

STOCK_FIELDS = {
    "vendor_name": {"scope": "header", "type": "str", "required": True, "synonyms": ["vendor", "firm", "agency", "distributor", "party"]},
    "vendor_gstin": {"scope": "header", "type": "str", "required": False, "synonyms": ["gstin", "gst no", "gst number", "tin"]},
    "division": {"scope": "header", "type": "enum", "required": True, "synonyms": ["company", "division", "brand", "cosmo", "pharma", "derma", "cosmoq", "pedia", "cosmocor", "dermacor"]},

    "product_name": {"scope": "stock", "type": "str", "required": True, "synonyms": ["item", "item name", "itemname", "description", "product", "particulars", "product name", "product description", "sku", "name", "product / company", "product/company", "prdnm", "d e s c r i p t i o n"]},
    "pack": {"scope": "stock", "type": "str", "required": True, "synonyms": ["pack", "packing", "size", "uom", "unit", "packsize"]},
    "opening_stock": {"scope": "stock", "type": "num", "required": True, "synonyms": ["opening", "opening qty", "op stock", "op qty", "opening bal", "opening balance", "opening stock", "o s", "op", "op bal", "open", "opstk"]},
    "purchase_stock": {"scope": "stock", "type": "num", "required": True, "synonyms": ["purchase", "purchase qty", "pur qty", "purch", "receipt", "received", "recd", "inward", "pur stock", "purchases", "purchase stock", "in", "rcvd qty", "p qty", "receive", "receive qty", "receive quantity", "recp", "inw qty", "purstk", "purtot", "pur tot", "rcpts", "receipts", "purc"]},
    # "purfree" — Marg glued "PURFREE QTY" header (LAXMI): "purfree qty" contains-matches this
    # (0.88, earlier field) so it binds purchase_free, freeing the real sale-free column. Do
    # NOT add the spaced "purfree qty"/"pur free qty" — those contain the substring "free qty",
    # which would steal a bare "FREE QTY" sales-free column (SHRI RAM) into purchase_free.
    "purchase_free": {"scope": "stock", "type": "num", "required": True, "synonyms": ["purchase free", "pur free", "free purchase", "pur fr", "p free", "purch free", "scheme purchase", "receipt free", "purscm", "pur scm", "purfree"]},
    "purchase_return": {"scope": "stock", "type": "num", "required": True, "synonyms": ["purchase return", "pur return", "pur ret", "p return", "purch return", "prchs return", "pr return", "prtot", "pr tot", "b e pr", "pretqty"]},
    # "sl qty" — SHRI RAM JEE "SL QTY" sales column (fuzzy <0.62 vs every synonym, so it fell
    # to raw_ while "NET SALE VALUE" stole sales_qty via the 0.88 "sale" contains rule). Exact.
    "sales_qty": {"scope": "stock", "type": "num", "required": True, "synonyms": ["sales qty", "sale qty", "sold qty", "sales quantity", "issue", "issued", "outward", "sale", "sales", "net sales qty", "sales stock", "out", "issue qty", "s qty", "s.qty", "saletot", "sale tot", "sl qty"]},
    "sales_value": {"scope": "stock", "type": "num", "required": True, "synonyms": ["sales value", "sale value", "sales amt", "sales amount", "sale amt", "net sales", "sales val", "sale amount", "value", "s val", "saleamt", "saleval", "sale val", "salev", "gross amount", "grs amt", "sa val", "sa value", "net sale value"]},
    # "scm" (MediVision "Scm" scheme/free column) -> sales_free. NOTE this layout prints
    # TWO identical "Scm" columns (purchase-scheme + sales-scheme); a flat header can't tell
    # them apart, so header matching binds only one — the positional medivision_stock_sales
    # parser is what splits them correctly. Bare "scm" was previously unmatched in stock.
    # "salefr" — Marg glued "SaleFr" header (AMBIKA family): only spaced "sale fr" existed,
    # so the glued form lost to sales_qty's "sale" 0.88 contains-steal and sales_free went 0
    # on every row. Exact 1.0 fixes it; 6-char but used for EXACT match, not fuzzy.
    # "sale free qty" — LAXMI "SALE FREE QTY": ties sales_qty (0.88 via "sale") and loses the
    # used-key race to the "SALE-1" column; the exact token lifts it to 1.0 so it binds here.
    "sales_free": {"scope": "stock", "type": "num", "required": True, "synonyms": ["sales free", "sale free", "free sales", "sale fr", "s free", "scheme qty", "sch qty", "scheme", "s sch", "free", "slscm", "sl scm", "scm", "salefr", "sale free qty"]},
    # bare "sr" removed as a synonym — it exact-matches the ubiquitous "Sr." serial-number
    # column and steals it into sales_return (a serial 1,2,3… added to closing wrecks
    # reconciliation). Real return columns still match via the specific synonyms below.
    "sales_return": {"scope": "stock", "type": "num", "required": True, "synonyms": ["sales return", "sale return", "sale ret", "sales ret", "s return", "sls return", "saleret", "salesret", "salesret.", "sales ret.", "srtot", "sr tot", "sretqty"]},
    # "bal qty" — CENTRAL AGENCIES (BlueFox) / C-Square "Stock And Sales" reports head the
    # closing column "Bal." over a "Qty" sub-row ("Bal. Qty" = Balance qty = closing). The
    # 2-token "bal qty" is specific (a bare "bal" would over-reach), and the disambiguated
    # "Op Bal" / "Opening Balance" still bind opening_stock via their EXACT 1.0 match.
    "closing_stock": {"scope": "stock", "type": "num", "required": True, "synonyms": ["closing", "closing qty", "cl stock", "cl qty", "closing bal", "closing balance", "closing stock", "c s", "cl", "balance", "bal qty", "closestock", "close", "c stk", "clstk", "curstk", "cur stk", "current stock", "cls stk", "cls stk qty", "clsg", "qoh", "qty on hand", "quantity on hand"]},
    # "bal val" / "bal value" — CENTRAL's closing-value column "Bal.Val" (normalized
    # "bal val"); without it the "value" substring mis-binds it to sales_value.
    # "closing value pur rate" — SHRI RAM JEE "CLOSING VALUE(PUR RATE)" normalizes to this;
    # without the exact token "value" mis-binds it to sales_value. Multi-token exact.
    "closing_stock_value": {"scope": "stock", "type": "num", "required": True, "synonyms": ["closing stock value", "closing value", "closing amt", "cl stock value", "cl value", "balance value", "bal val", "bal value", "closing val", "cl val", "clval", "c val", "cl amt", "qoh value", "qohvalue", "closing value pur rate"]},
    "hsn_code": {"scope": "stock", "type": "str", "required": False, "synonyms": ["hsn", "hsn code", "code", "product code", "pcod", "p cod"]},
    "batch_no": {"scope": "stock", "type": "str", "required": False, "synonyms": ["batch", "batch no", "lot"]},
    "expiry": {"scope": "stock", "type": "str", "required": False, "synonyms": ["expiry", "exp", "expiry date", "exp date", "m exp", "near exp", "nearexp"]},
    "mrp": {"scope": "stock", "type": "num", "required": False, "synonyms": ["mrp", "m r p"]},
    "rate": {"scope": "stock", "type": "num", "required": False, "synonyms": ["rate", "ptr", "sale rate"]},
    "gst_rate": {"scope": "stock", "type": "num", "required": False, "synonyms": ["gst", "gst rate", "gst%", "tax%"]},
    "opening_value": {"scope": "stock", "type": "num", "required": False, "synonyms": ["opening value", "op value", "opening val", "op amt", "openval", "open val"]},
    "purchase_value": {"scope": "stock", "type": "num", "required": False, "synonyms": ["purchase value", "pur value", "receipt value", "value(prate)", "purc val", "purc value"]},
    "sales_return_value": {"scope": "stock", "type": "num", "required": False, "synonyms": ["sales return value", "sale return value", "sr value"]},
    "exp_damage": {"scope": "stock", "type": "num", "required": False, "synonyms": ["exp dmg", "exp/dmg", "expiry damage", "expiry/damage", "expired damage", "expired", "damage", "dmg"]},
    "shortage": {"scope": "stock", "type": "num", "required": False, "synonyms": ["shortage", "short", "short qty"]},
    "total_stock": {"scope": "stock", "type": "num", "required": False, "synonyms": ["total stock", "total", "total qty", "tot stk", "tot stock"]},
    "order_qty": {"scope": "stock", "type": "num", "required": False, "synonyms": ["order qty", "order qty.", "order quantity", "order", "reorder", "reorder qty", "replenishment", "replenishment qty", "replqty", "repl qty"]},
    "net_amount": {"scope": "stock", "type": "num", "required": False, "synonyms": ["net amount", "net amt"]},
    "discount_amount": {"scope": "stock", "type": "num", "required": False, "synonyms": ["s disc", "disc", "discount", "scheme disc", "sch disc", "prod dis", "prod.dis"]},
    "discount_percent": {"scope": "stock", "type": "num", "required": False, "synonyms": ["discount percent", "disc pct", "disc %"]},
    "report_type_label": {"scope": "header", "type": "str", "required": False, "synonyms": ["report type", "report for", "statement type", "title"]},
}
CANONICAL_FIELDS = {"party": PARTY_FIELDS, "stock": STOCK_FIELDS}
SYNONYMS = {
    report_type: {key: [key.replace("_", " "), *spec["synonyms"]] for key, spec in fields.items()}
    for report_type, fields in CANONICAL_FIELDS.items()
}

INT_FIELDS = {
    "qty", "free_qty", "claim_qty", 
    "opening_stock", "purchase_stock", "purchase_free", "purchase_return",
    "sales_qty", "sales_free", "sales_return", "closing_stock",
    "exp_damage", "shortage", "total_stock", "order_qty"
}

def required_fields(report_type):
    return [key for key, spec in CANONICAL_FIELDS[report_type].items() if spec["required"]]

def numeric_fields(report_type, required_only=False):
    return [
        key for key, spec in CANONICAL_FIELDS[report_type].items()
        if spec["type"] == "num" and (not required_only or spec["required"])
    ]

def enforce_schema(records, report_type="party"):
    """
    Enforce that all defined canonical fields exist in each record.
    Missing strings are initialized to "" and missing numbers to "0".
    For taxable_value, it will attempt to calculate qty * rate if missing.
    Date-typed fields are normalised to ISO YYYY-MM-DD (day-first for
    ambiguous numeric forms — Indian convention) via core.dates.to_iso_date,
    so raw DD/MM/YYYY strings never leave the engine and can't be
    month/day-swapped downstream.
    """
    from core.dates import to_iso_date

    schema = CANONICAL_FIELDS[report_type]
    for record in records:
        for field, spec in schema.items():
            val = record.get(field)
            if val is None or str(val).strip() == "":
                if spec["type"] == "num":
                    if field == "taxable_value":
                        try:
                            rate = float(record.get("rate", 0) or 0)
                            qty = float(record.get("qty", 0) or 0)
                            if rate and qty:
                                record[field] = f"{rate * qty:.2f}"
                            else:
                                record[field] = "0"
                        except (ValueError, TypeError):
                            record[field] = "0"
                    else:
                        record[field] = "0"
                else:
                    record[field] = ""
            elif spec["type"] == "num" and field in INT_FIELDS:
                try:
                    f = float(str(val).strip().replace(',', ''))
                    # Preserve genuine fractional Busy/Tally quantities (e.g. 95.50 pcs);
                    # only collapse to int when already integral. Rounding 95.50->96 broke
                    # qty/free and Grand-Total reconciliation.
                    record[field] = str(int(f)) if f == int(f) else str(f)
                except (ValueError, TypeError):
                    pass
            elif spec["type"] == "date":
                record[field] = to_iso_date(val)
