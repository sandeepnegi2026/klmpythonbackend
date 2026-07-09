"""KLM "STOCK & SALES" abbreviated OP/PI/Sale/ST(Out)/CLQty export (DHRUVI HEALTHCARE
PVT LTD — KLM HO 1.xlsx).

Single header row (row index 4), exact tokens:
  Product Name | Packing | OP | OPVal | PI | PIVal | Sale | SI Value | ST (Out) |
  ST Value | CLQty | CLValue

Why a dedicated positional parser: the generic ``tabular`` header mapper drops the only
inflow column. ``map_headers_indexed`` resolves OP->opening_stock (exact), Sale->sales_qty
(exact), CLQty->closing_stock (fuzzy, correct) but PI->None (no purchase synonym matches
the bare abbreviation "PI"), PIVal->None, ST (Out)->None (the ambiguous "contains sales"
match is rejected), ST Value->None, CLValue->None. With PI (the sole inflow) dropped,
closing = OP - Sale for most rows and every moving row fails the sanity equation.

This parser maps ONLY the known abbreviated headers by exact text:
  Product Name -> product_name (strip leading dots — the export indents products with
                  leading '.' characters, e.g. '...NIOSALIC F CREAM 10GM')
  Packing      -> pack
  OP           -> opening_stock
  OPVal        -> opening_value
  PI           -> purchase_stock       (the sole inflow)
  PIVal        -> purchase_value
  Sale         -> sales_qty
  SI Value     -> sales_value
  ST (Out)     -> sales_free            (an OUT quantity that SUBTRACTS from closing;
                  mapped to sales_free so the reconciliation equation
                  closing = opening + purchase - sales - sales_free matches the ERP's
                  own closing = OP + PI - Sale - ST(Out))
  CLQty        -> closing_stock
  CLValue      -> closing_stock_value

Reconciles: CLQty = OP + PI - Sale - ST(Out) holds on 228/257 product rows (0.887 >>
0.50 floor); the ~29 off-by-1..2 rows are genuine vendor quirks. Value totals are
available for corroboration (row 282 grand "Total Value": OPVal 974895.51 /
PIVal 1208946.81 / SI Value 1126664.13 / ST Value 336130.2 / CLValue 787206.13).

Skipped rows:
  - "Division : <code>" band rows carry only col 0 -> the <=1 non-empty guard drops them.
  - "Total Value  (...)" per-division footers and the grand "Total Value" footer carry an
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
    "st(out)":     "sales_free",          # OUT quantity that subtracts from closing
    "clqty":       "closing_stock",
    "clvalue":     "closing_stock_value",
    # "ST Value" (out-value) intentionally omitted — no canonical outflow-value field.
}


def _norm(cell):
    return cell_text(cell).lower().replace(" ", "")


def parse_klm_op_pi_clqty_xlsx(rows):
    header_idx = None
    for idx in range(min(len(rows), 60)):
        cells = [_norm(c) for c in rows[idx]]
        # Unique signature of this export: the OP/PI/Sale/ST(Out)/CLQty abbreviation set
        # on one header row.
        if all(tok in cells for tok in ("op", "pi", "sale", "st(out)", "clqty")):
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
        # "Total Value (...)" per-division + grand footers start with "total".
        if not product or is_subtotal(product):
            continue
        # Strip the leading indentation dots the export prefixes product names with.
        product = product.lstrip(".").strip()
        if not product:
            continue
        record["product_name"] = product
        records.append(record)

    return records, detected
