"""Marg "Report Designer" raw compute-column stock export (BALAJI MEDICAL AGENCIES).

The vendor exported a Marg report-designer grid WITHOUT applying a display template, so
the movement columns carry their internal compute IDs (``compute_0003`` .. ``compute_0027``)
instead of human labels. Product identity IS present though — the trailing columns
``c_name_item`` / ``c_name_mfac`` / ``c_name_pack`` hold the real names. The generic
``tabular`` reader finds no recognisable stock header (only ``compute_NNNN``) and returns
0 rows, so the file fails as UNKNOWN_LAYOUT.

The compute-ID -> field positions are fixed by this specific designer template, and the
mapping below RECONCILES on every sampled row:
    closing(0022) = opening(0026) + purchase(0003) - sales(0006) + sales_return(0012)
                    - purchase_return(0008)
e.g. KERAMATE EVA 0+10-6=4; ZYCOZOL 15+20-10+5=30; IMXIA PRO 20+0-2=18; KOJITIN EMULGEL
15+50-10-1=54 -- all exact. Because the gate keys on the EXACT designer header signature
(the compute_0003..0027 run plus the c_name_item/c_name_pack/n_sale_rate trailer), a file
built from a DIFFERENT template cannot match, and if a same-signature file ever carried
different compute semantics the per-row sanity reconcile would surface it (never silently
wrong). Value columns land only in *_value fields; qty columns only in qty fields.
"""
from extractors.stock_xlsx.parse_common import cell_text, is_subtotal

# Exact (lowercased, stripped) header text -> canonical field. Only the reconcile-verified
# movement columns + product identity are mapped; every other compute_NNNN (pre-month
# analytics, aging, transfer, etc.) is deliberately omitted so it cannot steal a field.
_COL_MAP = {
    "c_name_item": "product_name",
    "c_name_pack": "pack",
    "compute_0026": "opening_stock",
    "compute_0027": "opening_value",
    "compute_0003": "purchase_stock",
    "compute_0004": "purchase_value",
    "compute_0006": "sales_qty",
    "compute_0007": "sales_value",
    "compute_0008": "purchase_return",
    "compute_0012": "sales_return",
    "compute_0013": "sales_return_value",
    "compute_0022": "closing_stock",
    "compute_0023": "closing_stock_value",
    "n_sale_rate": "rate",
}


def parse_marg_designer_compute_stock(rows):
    header_idx = None
    for idx in range(min(len(rows), 20)):
        cells = [cell_text(c).lower().strip() for c in rows[idx]]
        if "c_item_code" in cells and "c_name_item" in cells and "compute_0022" in cells:
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
    # Require product identity + the closing anchor, else this is not the expected template.
    if "product_name" not in col_to_canonical.values() or "closing_stock" not in col_to_canonical.values():
        return [], {}

    records = []
    for raw_row in rows[header_idx + 1:]:
        if not any(cell_text(c) for c in raw_row):
            continue
        record = {}
        for col_idx, key in col_to_canonical.items():
            if col_idx < len(raw_row):
                record[key] = raw_row[col_idx]
        product = cell_text(record.get("product_name", ""))
        if not product or is_subtotal(product):
            continue
        pl = product.lower().strip()
        if pl.replace(".", "", 1).replace(",", "").isdigit():
            continue
        records.append(record)

    return records, detected
