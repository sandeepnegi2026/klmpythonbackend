"""KLM ERP "Sale & Stock statement" qty-only grid export (EMAMI FRANK ROSS).

Single header row (one physical column each, no split/merge):
  Item Code | Mfac Name | Item Name | Packing | Qpb | OpStk | Pur Qty |
  Branch Return | Out Qty | StkAdj | Closing Stock

Semantics (verified across every data row of the sample):
  Closing Stock = OpStk + Pur Qty + Branch Return - Out Qty - StkAdj
``StkAdj`` is a signed stock adjustment printed as its literal value (0 or
negative here, e.g. -1); the vendor SUBTRACTS it, so a negative StkAdj adds the
adjustment back. There are NO free-qty columns and NO rupee-value columns —
this is a pure quantity movement statement.

Why a dedicated positional parser rather than the generic ``tabular`` mapper:
  * "Branch Return" is an INWARD transfer that ADDS to stock, but the generic
    header matcher would drop it (no clean synonym) so closing would never
    reconcile on rows with a branch return.
  * "Out Qty" fuzzy-collides with nothing clean; "StkAdj" has no canonical
    home; "Qpb" (qty-per-box) is informational and must never land in a qty
    field. Mapping only the known columns by exact header text guarantees the
    movement columns bind correctly.

Field mapping chosen so the ENGINE's stock sanity equation
    expected = opening + purchase + purchase_free - purchase_return
               - sales - sales_free + sales_return
reproduces the vendor's closing arithmetic exactly:
    OpStk         -> opening_stock
    Pur Qty       -> purchase_stock
    Branch Return -> purchase_free   (inward: the equation ADDS purchase_free)
    Out Qty       -> sales_qty       (the equation SUBTRACTS sales_qty)
    StkAdj        -> purchase_return  (the equation SUBTRACTS purchase_return,
                                       so the raw StkAdj value reproduces the
                                       vendor's "- StkAdj" term exactly — a
                                       negative StkAdj is thus added back)
    Closing Stock -> closing_stock
    Item Name     -> product_name
    Packing       -> pack
    Item Code     -> hsn_code (product code)
    Mfac Name     -> (dropped; always the manufacturer, not a stock field)
"""
from extractors.stock_xlsx.parse_common import cell_text, is_subtotal

# Exact (lowercased, stripped) header text -> canonical field. Anything not
# listed (Qpb qty-per-box, Mfac Name manufacturer) is deliberately omitted so
# it can never steal a movement field.
_COL_MAP = {
    "item code": "hsn_code",
    "item name": "product_name",
    "packing": "pack",
    "opstk": "opening_stock",
    "pur qty": "purchase_stock",
    "branch return": "purchase_free",   # inward transfer -> ADDED by sanity eq
    "out qty": "sales_qty",             # outward -> SUBTRACTED by sanity eq
    "stkadj": "purchase_return",        # signed adj -> SUBTRACTED by sanity eq,
                                        # matching the vendor's "- StkAdj" term
                                        # (a negative StkAdj is thus added back)
    "closing stock": "closing_stock",
}

# Header signature cells that MUST all be present on the header row for this to
# be the right sheet — the unique KLM "Sale & Stock statement" column combo.
_REQUIRED_HEADER = {"opstk", "branch return", "out qty", "stkadj", "closing stock"}


def parse_klm_sale_stock_stmt(rows):
    header_idx = None
    for idx in range(min(len(rows), 40)):
        cells = {cell_text(c).lower().strip() for c in rows[idx]}
        if _REQUIRED_HEADER.issubset(cells):
            header_idx = idx
            break
    if header_idx is None:
        return [], {}

    col_to_canonical = {}
    detected = {}
    for i, cell in enumerate(rows[header_idx]):
        key = _COL_MAP.get(cell_text(cell).lower().strip())
        if key and key not in col_to_canonical.values():
            col_to_canonical[i] = key
            detected[cell_text(cell)] = key
    if (
        "product_name" not in col_to_canonical.values()
        or "closing_stock" not in col_to_canonical.values()
        or "opening_stock" not in col_to_canonical.values()
    ):
        return [], {}

    records = []
    for raw_row in rows[header_idx + 1:]:
        if not any(cell_text(c) for c in raw_row):
            continue
        if sum(1 for c in raw_row if cell_text(c)) <= 1:
            continue
        record = {}
        for col_idx, key in col_to_canonical.items():
            if col_idx < len(raw_row):
                record[key] = raw_row[col_idx]
        product = cell_text(record.get("product_name", ""))
        if not product or is_subtotal(product):
            continue
        pl = product.lower().strip()
        if any(pl.startswith(k) for k in (
            "opening value", "purchase value", "close value", "sale value",
            "value in rs", "quantity", "---", "page total", "grand total",
            "total", "company", "division", "manufacturer", "item name",
        )):
            continue
        # A row whose "product" is purely numeric is a stray total/serial line.
        if pl.replace(".", "", 1).replace(",", "").isdigit():
            continue
        records.append(record)

    return records, detected
