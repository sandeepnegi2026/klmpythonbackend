"""Clean Open/Receipt/Issue/Closing qty+value grid keyed by underscored field abbreviations
(CHOUDHARY MEDICAL AGENCIES, KLM "KLM_COSMO_ORTHO.XLS" BIFF export).

Header (single row)::

    item_name | op_stock | op_value | rec_qty | rec_value | iss_qty | iss_value | clos_qty | clos_value

The generic `tabular` reader maps opening/receipt correctly but the shared header-synonym
matcher's "contains" heuristic greedily collapses EVERY value column onto sales_value
(rec_value / iss_value / clos_value all score 0.88 against a sales synonym) and both remaining
qty columns onto sales_qty (iss_qty / clos_qty), so map_headers_indexed — which binds each
canonical field to a single best column — never assigns closing_stock, closing_stock_value or
purchase_value.  Closing then reads all-zero and every row with stock fails the sanity equation.

This dedicated parser maps ONLY these exact abbreviations by column index, so receipt->purchase
and issue->sales, and closing = opening + purchase - sales reconciles exactly (verified: every
row balances, e.g. EKRAN AQUA 0 + 6 - 2 = 4).  Keyed on the underscored abbreviation set
op_stock + rec_qty + iss_qty + clos_qty, which is unique to this export (the KLM
op_stk/pr_rec/cl_stk and op_bal/cl_bal families use different abbreviations), so it can never
steal another vendor's grid.
"""
from extractors.stock_xlsx.parse_common import cell_text, is_subtotal

# header label (lowercased, stripped) -> canonical field.
_HEADER_MAP = {
    "item_name": "product_name",
    "op_stock": "opening_stock",
    "op_value": "opening_value",
    "rec_qty": "purchase_stock",
    "rec_value": "purchase_value",
    "iss_qty": "sales_qty",
    "iss_value": "sales_value",
    "clos_qty": "closing_stock",
    "clos_value": "closing_stock_value",
}


def _norm(text):
    return text.strip().lower()


def parse_stock_op_rec_iss_clos_grid(rows):
    # Locate the header row: the one whose cells include item_name + clos_qty.
    header_idx = None
    col_field = {}
    for idx in range(min(len(rows), 40)):
        cells = [cell_text(c) for c in rows[idx]] if rows[idx] else []
        norms = [_norm(c) for c in cells]
        if "item_name" in norms and "clos_qty" in norms and "op_stock" in norms:
            header_idx = idx
            col_field = {i: _HEADER_MAP[n] for i, n in enumerate(norms) if n in _HEADER_MAP}
            break
    if header_idx is None or "product_name" not in col_field.values():
        return [], {}

    name_idx = next(i for i, f in col_field.items() if f == "product_name")

    records = []
    for raw_row in rows[header_idx + 1:]:
        cells = [cell_text(c) for c in raw_row] if raw_row else []
        if name_idx >= len(cells):
            continue
        name = cells[name_idx].strip()
        if not name or is_subtotal(name):
            continue

        record = {}
        for i, field in col_field.items():
            if i < len(cells):
                record[field] = cells[i].strip()
        # Default the canonical numeric fields that were blank in this row to "0".
        for field in ("opening_stock", "opening_value", "purchase_stock", "purchase_value",
                      "sales_qty", "sales_value", "closing_stock", "closing_stock_value"):
            if not record.get(field):
                record[field] = "0"
        records.append(record)

    detected = {raw: _HEADER_MAP[raw] for raw in _HEADER_MAP}
    return records, detected
