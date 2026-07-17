"""DEEPA AGENCIES "SALE_DTL" abbreviated-header stock/sales export (klm.xlsx).

Single header row (sheet name and first row both read ``SALE_DTL``):
  ITEM_CODE | ITEM_NAME | MANU_CODE | MANU_NAME | SALE_QTY | BON_QTY |
  DIS_PERC | DIS_AMT | SPR_PTR | STAX_PERC | SRET_QTY | PACK_SIZE |
  OP_BAL | CL_BAL | ACODE | FROM_DATE | TO_DATE

Why a dedicated positional parser rather than the generic ``tabular`` mapper:
  * ``CL_BAL`` is the closing QTY, but the fuzzy header matcher scores
    ``match_header('CL_BAL','stock')`` as ``closing_stock_value`` (0.68 — the
    'BAL' vs 'value' fuzz wins), so the closing quantity lands in the value
    field and ``closing_stock`` reads 0 -> every one of the 176 rows fails the
    sanity equation.
  * ``BON_QTY`` (bonus / free-out) fuzzy-maps to ``opening_stock`` (0.63), a
    false positive that further corrupts the movement columns.
  Mapping only the known headers by EXACT text guarantees each column binds
  correctly.

Field mapping (only known columns; DIS_PERC/DIS_AMT/ACODE/FROM_DATE/TO_DATE/
ITEM_CODE/MANU_CODE are deliberately omitted so they can never steal a field):
    ITEM_NAME  -> product_name
    MANU_NAME  -> division
    PACK_SIZE  -> pack
    OP_BAL     -> opening_stock
    CL_BAL     -> closing_stock   (the closing QTY — fixes the mis-bind)
    SALE_QTY   -> sales_qty       (SUBTRACTED by the sanity equation)
    SRET_QTY   -> sales_return    (INWARD return — ADDED by the sanity equation)
    BON_QTY    -> sales_free      (bonus is a free-out — SUBTRACTED)
    SPR_PTR    -> rate
    STAX_PERC  -> gst_rate

The report carries NO purchase column, so the sanity equation cannot fully
reconcile (opening is mostly 0 with no inflow). The existing
``no_inflow_columns`` / value-corroborated triage downgrade carries such a
sheet to AMBER (never GREEN). Verified structurally: KENZ LOTION OP_BAL 0,
SALE_QTY 24, CL_BAL 43 — CL_BAL is the closing quantity.
"""
from extractors.stock_xlsx.parse_common import cell_text, is_subtotal

# Exact (lowercased, stripped) header text -> canonical field. Anything not
# listed (ITEM_CODE, MANU_CODE, DIS_PERC, DIS_AMT, ACODE, FROM_DATE, TO_DATE)
# is deliberately omitted so it can never steal a movement field.
_COL_MAP = {
    "item_name": "product_name",
    "manu_name": "division",
    "pack_size": "pack",
    "op_bal": "opening_stock",
    "cl_bal": "closing_stock",   # the closing QTY (fuzzy mis-binds to value)
    "sale_qty": "sales_qty",     # outward -> SUBTRACTED by sanity eq
    "sret_qty": "sales_return",  # inward return -> ADDED by sanity eq
    "bon_qty": "sales_free",     # bonus free-out -> SUBTRACTED by sanity eq
    "spr_ptr": "rate",
    "stax_perc": "gst_rate",
}

# Header signature cells that MUST all be present on the header row — the unique
# DEEPA/KLM "SALE_DTL" abbreviation combo.
_REQUIRED_HEADER = {"sale_qty", "op_bal", "cl_bal", "sret_qty", "bon_qty"}


def parse_klm_sale_dtl_xlsx(rows):
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
            "total", "company", "division", "manufacturer", "item_name",
        )):
            continue
        # A row whose "product" is purely numeric is a stray total/serial line.
        if pl.replace(".", "", 1).replace(",", "").isdigit():
            continue
        records.append(record)

    return records, detected
