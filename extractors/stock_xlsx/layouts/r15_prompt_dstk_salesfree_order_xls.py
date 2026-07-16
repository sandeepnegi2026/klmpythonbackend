"""Prompt ERP "Stock Statement (Datewise)" for KLM — the SALES-FREE + ClStk(Qty/Amount)
variant (ALL CARE MEDICINES, "excel stock klm.xls").

This is the compact-header sibling of ``prompt_dstk_free_xlsx`` (V.G.RAJA). Both carry the
"Stock Statement (Datewise)" title and a two-row header, but the two exports differ in
BOTH the column set and the group/sub-header alignment:

  * ``prompt_dstk_free_xlsx``: the GROUP header aligns with the data by index; Sales is a
    single Qty column; ClStk is a single Qty column; the analytics tail is A3Mn / Favourite.
    Its gate requires "favourite".

  * THIS export (ALL CARE): the GROUP header is COMPACT and does NOT align with the data —

        row (group): Product Name | | | Pack | OpStk | Pur | Sales | ClStk         (7 cells)
        row (sub)  :               |   |    | Qty  | Qty  | Qty | Free | Inst | Qty | Amount | A3Mn | Order(s)
        row (data) : 1 | BLEMGUARD FACE SERUM | | 30ML | 16 | 0 | 2 | 0 | 0 | 14 | 6454.28 | 2 | 0/0=0

    So Sales spans THREE physical columns (Qty / Free / Inst) and ClStk spans TWO
    (Qty / Amount). The group header "ClStk" cell sits at the grid index the DATA row uses
    for Sales-Free, so any group-index mapping (like the sibling parser) reads
    closing_stock from the Sales-Free column (=0 on most rows) and never sees the real
    closing qty at col 9. Verified: routing this file to ``prompt_dstk_free_xlsx`` reads
    closing_stock='0' for every product -> 100% sanity fail (RED).

The physical column positions align with the SUB-header row, so we bind by walking the
sub-header row and consuming the fixed movement sequence Qty | Qty | Qty | Free | Inst |
Qty | Amount from the first "Qty" cell onward:

    OpStk.Qty (1st Qty)  -> opening_stock
    Pur.Qty   (2nd Qty)  -> purchase_stock   (purchase inflow; may be negative = adjustment)
    Sales.Qty (3rd Qty)  -> sales_qty         (outflow -)
    Sales.Free           -> sales_free        (free-on-sale, outflow -)
    Sales.Inst           -> ignored           (always 0 in this export; not part of movement)
    ClStk.Qty (4th Qty)  -> closing_stock
    ClStk.Amount         -> closing_stock_value (rupee value; NEVER a quantity)

The A3Mn / Order(s) analytics tail is deliberately dropped. Product name is col 1
(col 0 is the serial). Reconciles EXACTLY on all rows:
    closing = opening + purchase - sales_qty - sales_free
(BLEMGUARD-TX: 11 + 0 - 3 - 1 = 7 = ClStk.Qty; verified 167/167 product rows balance).

Gate token (compact, sub-header run unique to this variant, distinct from the sibling's
"favourite"): "stockstatement(datewise)" + OpStk/ClStk group + the Sales-group "free" +
"inst" sub-labels + the "order(s)" analytics tail, WITHOUT "favourite".
"""
from extractors.stock_xlsx.parse_common import cell_text, is_subtotal, to_number

_STOP_PRODUCT_PREFIXES = (
    "total", "amount", "bills", "opening value", "purchase value", "close value",
    "sale value", "value in rs", "quantity", "grand total", "page total",
    "company", "division", "manufacturer", "powered by", "for, company",
    "authorized", "authorised",
)


def detect(rows):
    flat = " ".join(
        " ".join(cell_text(c) for c in row) for row in rows[:60]
    ).lower().replace(" ", "")
    return (
        "stockstatement(datewise)" in flat
        and "opstk" in flat
        and "clstk" in flat
        and "order(s)" in flat
        and "favourite" not in flat
        # the Sales-group sub-labels that push closing to its own column
        and "free" in flat
        and "inst" in flat
    )


def _find_group_header(rows):
    """Return the group-header row index (carries OpStk/Pur/Sales/ClStk)."""
    for idx in range(min(len(rows), 60)):
        cells = [cell_text(c).lower().strip() for c in rows[idx]]
        if (
            "opstk" in cells and "pur" in cells
            and "sales" in cells and "clstk" in cells
        ):
            return idx
    return None


def parse_prompt_dstk_salesfree_order_xls(rows):
    hdr = _find_group_header(rows)
    if hdr is None:
        return [], {}
    sub_idx = hdr + 1
    if sub_idx >= len(rows):
        return [], {}

    sub = [cell_text(c).lower().strip() for c in rows[sub_idx]]
    # Walk the sub-header row to bind the fixed movement sequence positionally, anchored on
    # the first "Qty" cell:  Qty | Qty | Qty | Free | Inst | Qty | Amount
    qty_cols = [i for i, c in enumerate(sub) if c == "qty"]
    free_cols = [i for i, c in enumerate(sub) if c == "free"]
    amount_cols = [i for i, c in enumerate(sub) if c == "amount"]
    if len(qty_cols) < 4 or not free_cols or not amount_cols:
        return [], {}

    col = {
        "opening_stock": qty_cols[0],   # OpStk Qty
        "purchase_stock": qty_cols[1],  # Pur Qty
        "sales_qty": qty_cols[2],       # Sales Qty
        "sales_free": free_cols[0],     # Sales Free
        "closing_stock": qty_cols[3],   # ClStk Qty
        "closing_stock_value": amount_cols[0],  # ClStk Amount
    }

    def num(raw_row, key):
        i = col[key]
        if i >= len(raw_row):
            return 0.0
        return to_number(raw_row[i]) or 0.0

    records = []
    for raw_row in rows[sub_idx + 1:]:
        if not any(cell_text(c) for c in raw_row):
            continue
        # Data rows carry a bare integer serial in col 0 and the product in col 1.
        serial = cell_text(raw_row[0]) if raw_row else ""
        if not serial.isdigit():
            # division bands ("KLM PHARMACEUTICAL" in col 0) and footers ("Total:"/"Bills:"
            # in col 2, empty col 0) never have a bare-integer serial in col 0.
            continue
        product = cell_text(raw_row[1]) if len(raw_row) > 1 else ""
        if not product:
            continue
        pl = product.lower().strip()
        if is_subtotal(product) or pl.startswith(_STOP_PRODUCT_PREFIXES):
            continue

        rec = {
            "product_name": product,
            "pack": cell_text(raw_row[3]) if len(raw_row) > 3 else "",
            "opening_stock": num(raw_row, "opening_stock"),
            "purchase_stock": num(raw_row, "purchase_stock"),
            "sales_qty": num(raw_row, "sales_qty"),
            "sales_free": num(raw_row, "sales_free"),
            "closing_stock": num(raw_row, "closing_stock"),
            "closing_stock_value": num(raw_row, "closing_stock_value"),
        }
        records.append(rec)

    detected = {
        "Product Name": "product_name",
        "Pack": "pack",
        "OpStk Qty": "opening_stock",
        "Pur Qty": "purchase_stock",
        "Sales Qty": "sales_qty",
        "Sales Free": "sales_free",
        "ClStk Qty": "closing_stock",
        "ClStk Amount": "closing_stock_value",
    }
    return records, detected
