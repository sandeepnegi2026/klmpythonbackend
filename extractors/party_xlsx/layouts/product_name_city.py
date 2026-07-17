"""
Product / Name / City columnar party-wise Excel (e.g. the SALEAPX export).

A flat per-row sale table whose header is roughly:

    PRODUCT | PACK | NAME | CITY | QTY | FREE | AMOUNT | GST | NETAMT

Each row is one product sold to one customer; the customer is the ``NAME`` column
and the location the ``CITY`` column. There is no party band and no party header,
and after each product group there is a blank-product subtotal row (only the numeric
columns filled).

The generic header mapper sends a bare ``NAME`` column to ``vendor_name`` — its
"vendor name" synonym wins the tie against "party name" purely by dict order — so the
customer never lands in ``party_name`` (-> MISSING_REQUIRED_FIELD:party_name). This
layout reuses ``map_headers`` for every column and fixes only that one thing: in a
per-row party table the firm-name column IS the customer, so a ``vendor_name`` column
is reassigned to ``party_name`` when no real party column was mapped. Per-product
subtotal rows and the grand ``TOTAL`` row (blank product cell) are skipped.
"""
from core.header_match import map_headers

from extractors.party_xlsx.header_detect import detect_header_row
from extractors.party_xlsx.parse_common import cell_text, is_subtotal


def parse_product_name_city(rows):
    header_idx = detect_header_row(rows, min_matches=4)
    if header_idx is None:
        return [], {}

    headers = [str(h) if cell_text(h) else f"col_{i}" for i, h in enumerate(rows[header_idx])]
    header_map = map_headers(headers, "party")
    detected = {raw: info["canonical"] for raw, info in header_map.items()}

    col = {}
    for idx, raw in enumerate(headers):
        key = detected.get(raw)
        if key and key not in col:
            col[key] = idx

    # Per-row party table: the firm-name column is actually the customer.
    if "party_name" not in col and "vendor_name" in col:
        col["party_name"] = col.pop("vendor_name")
        detected = {
            raw: ("party_name" if canonical == "vendor_name" else canonical)
            for raw, canonical in detected.items()
        }

    records = []
    for raw in rows[header_idx + 1 :]:
        if not raw:
            continue
        record = {key: (raw[idx] if idx < len(raw) else "") for key, idx in col.items()}
        product = cell_text(record.get("product_name", ""))
        if not product or is_subtotal(product):
            continue
        records.append(record)
    return records, detected
