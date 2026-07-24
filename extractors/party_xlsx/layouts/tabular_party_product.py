from core.header_match import map_headers

from extractors.party_xlsx.header_detect import detect_header_row
from extractors.party_xlsx.parse_common import cell_text, is_numeric_qty, is_subtotal


def parse_tabular_party_product(rows):
    header_idx = detect_header_row(rows, min_matches=4)
    if header_idx is None:
        return [], {}
    headers = [str(h) if h else f"col_{i}" for i, h in enumerate(rows[header_idx])]
    header_map = map_headers(headers, "party")
    detected = {raw: info["canonical"] for raw, info in header_map.items()}
    col = {v: i for i, raw in enumerate(headers) for v in [detected.get(raw)] if v}

    records = []
    last_party = ""
    last_city = ""
    for raw_row in rows[header_idx + 1 :]:
        party = (
            raw_row[col["party_name"]]
            if "party_name" in col and col["party_name"] < len(raw_row)
            else ""
        )
        city = ""
        if "party_location" in col and col["party_location"] < len(raw_row):
            city = raw_row[col["party_location"]]
        elif "party_area" in col and col["party_area"] < len(raw_row):
            city = raw_row[col["party_area"]]
        product = (
            raw_row[col["product_name"]]
            if "product_name" in col and col["product_name"] < len(raw_row)
            else ""
        )
        party = cell_text(party)
        city = cell_text(city)
        product = cell_text(product)
        if party and not is_numeric_qty(party):
            last_party, last_city = party, city or last_city
        if not product or product == "0" or is_subtotal(product):
            continue
        if not last_party:
            continue
        record = {
            "party_name": last_party,
            "party_location": last_city,
            "product_name": product,
        }
        for key, idx in col.items():
            if key in record or idx >= len(raw_row):
                continue
            record[key] = raw_row[idx]
        records.append(record)
    return records, detected
