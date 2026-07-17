from extractors.stock_xlsx.parse_common import cell_text, is_subtotal, split_plus_qty, to_number


def detect(rows):
    """Gate: KLM "Stock and Sales Statement For Company : <DIVISION>" per-division .xls
    (SHRI SAI SURGICAL AGENCY / SHRREE SAI). The PAIRED-value sibling with a
    dedicated PFree AND SFree header AND NO Apr/May movement columns. See parse fn docstring.

    Gate token: the contiguous compact header run "opstkpurpfreesalesfreecurstk" which is
    unique to this export (Opstk|Pur|PFree|Sale|SFree|CurStk in that exact order, with the
    scheme columns PFree/SFree sitting BETWEEN Pur/Sale and CurStk). The two sibling KLM
    exports differ:
      * klm_opstk_apr_may_curstk_xls -> header is Opstk|Pur|Apr|May|Sale|CurStk (no PFree/SFree),
        so "pfree" and the contiguous "pfreesale" run never bind.
      * r15_klm_ss_pfree_purret_aprmay_sfree_adj_curstk_xls -> header is
        Opstk|Pur|PFree|PurRet|Apr|May|Sale|SFree|... so "pfreesale" is broken by PurRet/Apr/May.
    """
    flat = " ".join(
        " ".join(cell_text(c) for c in row) for row in rows[:12]
    ).lower().replace(" ", "")
    return (
        "productname" in flat
        and "opstkpurpfreesalesfreecurstk" in flat
    )


def parse_klm_ss_paired_opstk_pfree_sfree_curstk_xls(rows):
    """KLM "Stock and Sales Statement For Company : <DIVISION>" PAIRED-value per-division .xls
    (SHRI SAI SURGICAL AGENCY; e.g. "KLM PHARMACEUTICALS. PAED"). One book per division.

    Single header row (14 columns), exact text::

        S.No | Product Name | Packing | Opstk | Pur | PFree | Sale | SFree | CurStk |
        StkVal | OrdQty | SalVal | Exp | Rate

    In THIS export the free-goods ledger is carried INLINE as a "paid+free" pair inside the
    Opstk / Pur / Sale / CurStk cells (e.g. Opstk="35+35", Pur="140+160", Sale="10",
    CurStk="166+166"); the dedicated PFree/SFree header columns exist but are always blank
    (the ERP prints free inline instead). split_plus_qty peels each pair; a plain numeric
    cell splits to (n, 0.0).

    Movement -> canonical mapping (mapped by EXACT header text, positionally):
        Opstk  paid+free -> opening_stock   (TOTAL opening: op_paid + op_free)
        Pur    paid      -> purchase_stock  (purchase qty, inflow +)
        Pur    free      -> purchase_free   (free-on-purchase qty, inflow +)
        Sale   paid      -> sales_qty       (current-period sale qty, outflow -)
        Sale   free      -> sales_free      (free-on-sale qty, outflow -)
        CurStk paid+free -> closing_stock   (TOTAL closing: cl_paid + cl_free)
        StkVal -> closing_stock_value       (closing rupee value)
        SalVal -> sales_value               (sales rupee value)
        OrdQty -> order_qty
        Rate   -> rate

    Folding both the paid and the free half of Opstk/CurStk into opening_stock/closing_stock
    (while breaking Pur/Sale into their paid+free halves) keeps the two internal ledgers
    (paid: op_p+pur_p-sal_p=cl_p; free: op_f+pur_f-sal_f=cl_f) summed, so
        closing = opening + purchase + purchase_free - sales_qty - sales_free
    holds on every row (verified 27/27 rows of SHRI SAI PAED).

    This distinguishes it from two existing siblings whose header searches never bind here:
      * klm_opstk_apr_may_curstk_xls -- expects the Apr|May pair (which lives only in this
        book's SUMMARY footer + title, not the header), so its stricter header search finds
        no Apr/May column in the header row and returns 0 rows (this file's current RED).
      * r15_klm_ss_pfree_purret_aprmay_sfree_adj_curstk_xls -- requires PurRet and the
        Apr|May columns in the header, both absent here.

    NEVER derives a quantity from a value column (StkVal/SalVal stay value-only).
    """
    header_idx = None
    for idx, row in enumerate(rows[:150]):
        flat = " ".join(cell_text(c) for c in row).lower().replace(" ", "")
        if (
            "productname" in flat and "opstk" in flat and "pur" in flat
            and "pfree" in flat and "sale" in flat and "sfree" in flat
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
        elif key == "sale":
            col["sale"] = i
        elif key == "sfree":
            col["sfree"] = i
        elif key == "curstk":
            col["curstk"] = i
        elif key == "stkval":
            col["stkval"] = i
        elif key == "ordqty":
            col["ordqty"] = i
        elif key == "salval":
            col["salval"] = i
        elif key == "rate":
            col["rate"] = i

    # Require the core movement columns; if any are missing the header didn't line up.
    for req in ("product", "opstk", "pur", "sale", "curstk"):
        if req not in col:
            return [], {}

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

        # Peel each paired "paid+free" cell. Opstk/CurStk fold both halves into the
        # opening/closing TOTAL; Pur/Sale split their halves into paid vs free.
        op_paid, op_free = split_plus_qty(at(raw_row, "opstk"))
        pur_paid, pur_free_inline = split_plus_qty(at(raw_row, "pur"))
        sale_paid, sale_free_inline = split_plus_qty(at(raw_row, "sale"))
        cl_paid, cl_free = split_plus_qty(at(raw_row, "curstk"))

        # Dedicated PFree/SFree header columns are blank in this export but read them
        # defensively (they add to the inline free halves if the ERP ever populates them).
        pfree_col = to_number(at(raw_row, "pfree")) or 0.0
        sfree_col = to_number(at(raw_row, "sfree")) or 0.0

        rec = {
            "product_name": product,
            "pack": cell_text(at(raw_row, "pack")),
            "opening_stock": op_paid + op_free,
            "purchase_stock": pur_paid,
            "purchase_free": pur_free_inline + pfree_col,
            "sales_qty": sale_paid,
            "sales_free": sale_free_inline + sfree_col,
            "closing_stock": cl_paid + cl_free,
            "closing_stock_value": to_number(at(raw_row, "stkval")) or 0.0,
        }
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
        "PFree": "purchase_free",
        "Sale": "sales_qty",
        "SFree": "sales_free",
        "CurStk": "closing_stock",
        "StkVal": "closing_stock_value",
    }
    return records, detected
