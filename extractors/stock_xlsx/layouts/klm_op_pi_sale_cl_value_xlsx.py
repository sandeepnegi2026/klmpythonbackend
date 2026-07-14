"""KLM "STOCK & SALES" abbreviated OP/PI/Sale/CLQty qty+value grid — the OUT-less sibling
of ``klm_op_pi_clqty_xlsx`` (DHRUVI HEALTH CARE PVT LTD — KLM LABO / klm.xlsx).

Single header row (row index 4), exact tokens — note the ABSENCE of any ST (Out)/ST Value
outflow column that the ``klm_op_pi_clqty_xlsx`` export carries:
  Product Name | Packing | OP | OPVal | PI | PIVal | Sale | SI Value | CLQty | CLValue

Why a dedicated positional parser: the generic ``tabular`` header mapper drops the only
inflow column. ``map_headers_indexed`` resolves OP->opening_stock (exact), Sale->sales_qty
(exact), CLQty->closing_stock (fuzzy, correct) but PI->None (no purchase synonym matches
the bare abbreviation "PI"), PIVal->None, SI Value / CLValue->sales_value / closing value
collide. With PI (the sole inflow) dropped, closing = OP - Sale for every moving row and
the sanity equation fails wholesale (observed sanity ~0.35, RED).

This parser maps ONLY the known abbreviated headers by exact text:
  Product Name -> product_name (strip leading indentation '.' characters, matching the
                  sibling export's convention)
  Packing      -> pack
  OP           -> opening_stock
  OPVal        -> opening_value
  PI           -> purchase_stock       (the sole inflow)
  PIVal        -> purchase_value
  Sale         -> sales_qty
  SI Value     -> sales_value
  CLQty        -> closing_stock
  CLValue      -> closing_stock_value

Reconciles cleanly: this export has NO out-quantity column, so the ERP's own identity is
CLQty = OP + PI - Sale, which is exactly the reconciliation equation
(closing = opening + purchase - sales) with every free/return/out term 0. Verified 100/100
product rows balance on DHRUVI (sanity 1.000).

Printed grand "Total Value" footer (row 135) for value corroboration:
  OPVal 442883.28 / PIVal 338332.90 / SI Value 411152.41 / CLValue 350436.38.

Skipped rows:
  - "Division : <code>" band rows carry only col 0 -> the <=1 non-empty guard drops them.
  - "Total Value  (<code>)" per-division footers and the grand "Total Value" footer carry an
    empty product cell in col 0 with the label; both start with "total" -> is_subtotal.
"""
from extractors.stock_xlsx.parse_common import cell_text, is_subtotal

# Exact (lowercased, space-stripped) header text -> canonical field. Everything not listed
# is deliberately omitted so it cannot steal a canonical field.
_COL_MAP = {
    "productname": "product_name",
    "packing":     "pack",
    "op":          "opening_stock",
    "opval":       "opening_value",
    "pi":          "purchase_stock",
    "pival":       "purchase_value",
    "sale":        "sales_qty",
    "sivalue":     "sales_value",
    "clqty":       "closing_stock",
    "clvalue":     "closing_stock_value",
}


def _norm(cell):
    return cell_text(cell).lower().replace(" ", "")


def parse_klm_op_pi_sale_cl_value_xlsx(rows):
    header_idx = None
    for idx in range(min(len(rows), 60)):
        cells = [_norm(c) for c in rows[idx]]
        # Unique signature: the OP/OPVal/PI/PIVal/Sale/SI Value/CLQty/CLValue abbreviation
        # set on one header row, WITHOUT the ST(Out) column of the klm_op_pi_clqty sibling.
        if (
            all(tok in cells for tok in ("op", "opval", "pi", "pival", "sale",
                                         "sivalue", "clqty", "clvalue"))
            and "st(out)" not in cells
        ):
            header_idx = idx
            break
    if header_idx is None:
        return [], {}

    col_to_canonical = {}
    detected = {}
    for i, cell in enumerate(rows[header_idx]):
        key = _COL_MAP.get(_norm(cell))
        if key and key not in col_to_canonical.values():
            col_to_canonical[i] = key
            detected[cell_text(cell)] = key
    if (
        "product_name" not in col_to_canonical.values()
        or "closing_stock" not in col_to_canonical.values()
    ):
        return [], {}

    records = []
    for raw_row in rows[header_idx + 1:]:
        if not any(cell_text(c) for c in raw_row):
            continue
        # "Division : <code>" band rows carry only 1 non-empty cell.
        if sum(1 for c in raw_row if cell_text(c)) <= 1:
            continue
        record = {}
        for col_idx, key in col_to_canonical.items():
            if col_idx < len(raw_row):
                record[key] = raw_row[col_idx]
        product = cell_text(record.get("product_name", ""))
        # "Total Value (<div>)" per-division + grand footers start with "total".
        if not product or is_subtotal(product):
            continue
        # Strip any leading indentation dots the export may prefix product names with.
        product = product.lstrip(".").strip()
        if not product:
            continue
        record["product_name"] = product
        records.append(record)

    return records, detected
