"""KLM "Sales && Stock Statement Group..." qty+value grid whose SALES column is
labelled "Total" (GARG DISTRIBUTOR "klm st.xlsx").

Header (single row)::

    NO | NAME | OP QTY | OP AMT | PUR QTY | PUR AMT | Total QTY | Total AMT |
    CL QTY | CL AMT

Here "Total QTY/AMT" is NOT the usual opening+purchase cross-check — it is the
SALES movement: OP + PUR - Total = CL reconciles exactly on every reference row
(EKRAN AQUA 4+0-1=3; HERPIVAL-1GM 80+0-12=68; HERPIVAL-500 4+12-16=0), and
"Total AMT" equals the party register's sale amount for the same product
(EKRAN AQUA 277.97). The generic tabular reader leaves sales unbound (or binds
"Total" to total_stock), so closing never reconciles -> 100% SANITY_FAILED.

Division bands ("KLM COSMO" in the NAME column, numerics blank) are skipped.
Keyed on the exact compact header run, unique to this export.
"""
from extractors.stock_xlsx.parse_common import cell_text, is_subtotal

_HEADER_MAP = {
    "name": "product_name",
    "op qty": "opening_stock",
    "op amt": "opening_value",
    "pur qty": "purchase_stock",
    "pur amt": "purchase_value",
    "total qty": "sales_qty",
    "total amt": "sales_value",
    "cl qty": "closing_stock",
    "cl amt": "closing_stock_value",
}

_NUM_FIELDS = ("opening_stock", "opening_value", "purchase_stock", "purchase_value",
               "sales_qty", "sales_value", "closing_stock", "closing_stock_value")


def parse_stock_op_pur_total_cl_xlsx(rows):
    header_idx = None
    col_field = {}
    for idx in range(min(len(rows), 40)):
        cells = [cell_text(c) for c in rows[idx]] if rows[idx] else []
        norms = [c.strip().lower() for c in cells]
        if "op qty" in norms and "total qty" in norms and "cl qty" in norms:
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
        # Per-division subtotals print as "TOTAL:40" (caught by is_subtotal); the final
        # grand-total row prints as "GTotal:176" (Grand Total, no space) which is_subtotal
        # misses because it neither starts with "total" nor "grand total".
        if not name or is_subtotal(name) or name.lstrip().lower().startswith("gtotal"):
            continue
        record = {}
        for i, field in col_field.items():
            if i < len(cells):
                record[field] = cells[i].strip()
        # a division band ("KLM COSMO") carries a name but no numbers at all
        if not any(record.get(f) for f in _NUM_FIELDS):
            continue
        for field in _NUM_FIELDS:
            if not record.get(field):
                record[field] = "0"
        records.append(record)

    detected = {raw: f for raw, f in _HEADER_MAP.items()}
    return records, detected
