from core.header_match import map_headers

from extractors.party_xlsx.header_detect import detect_header_row
from extractors.party_xlsx.parse_common import (
    cell_text,
    is_subtotal,
    label_value,
    looks_like_date,
    split_party_area,
)


def parse_marg_register_excel(rows):
    header_idx = detect_header_row(rows, min_matches=3)
    if header_idx is None:
        return [], {}
    headers = [str(h) if h else f"col_{i}" for i, h in enumerate(rows[header_idx])]
    header_map = map_headers(headers, "party")
    detected = {raw: info["canonical"] for raw, info in header_map.items()}
    col = {v: i for i, raw in enumerate(headers) for v in [detected.get(raw)] if v}

    item_idx = col.get("product_name", 2)
    date_idx = col.get("invoice_date", 1)
    inv_idx = col.get("invoice_number", 0)
    records = []
    current_party = ""
    current_area = ""
    for raw_row in rows[header_idx + 1 :]:
        area_val = label_value(raw_row, "area")
        if area_val:
            current_area = area_val
            continue
        customer_val = label_value(raw_row, "customer")
        if customer_val:
            current_party, area_from_party = split_party_area(customer_val)
            if area_from_party:
                current_area = area_from_party
            continue
        label = cell_text(raw_row[0] if raw_row else "").lower().rstrip(" :")
        if label.startswith("mf") or label.startswith("manufacturer"):
            continue

        item = cell_text(raw_row[item_idx] if item_idx < len(raw_row) else "")
        date = cell_text(raw_row[date_idx] if date_idx < len(raw_row) else "")
        inv = cell_text(raw_row[inv_idx] if inv_idx < len(raw_row) else "")
        if not item:
            continue
        if not looks_like_date(date) and not inv:
            import re
            # Extract clean area from date column if present (e.g. 'JAMALPUR-       287')
            area_val = ""
            if date:
                area_val = re.sub(r'-\s*\d+\s*$', '', date).strip()
            
            # Clean party name from item column
            name_val = re.sub(r'[,\s]+(?:AHMEDABAD|AHEDABAD|KADI)[.\s]*$', '', item, flags=re.IGNORECASE).strip()
            if area_val:
                name_val = re.sub(rf'\s*\(\s*{re.escape(area_val)}\s*\)', '', name_val, flags=re.IGNORECASE).strip()
                if area_val.upper() in ('AMBAVADI', 'AMBAWADI'):
                    name_val = re.sub(r'\s*\(\s*AMBA[VW]ADI\s*\)', '', name_val, flags=re.IGNORECASE).strip()
                
                # Strip trailing area name
                if name_val.upper().endswith(area_val.upper()):
                    name_val = name_val[:len(name_val)-len(area_val)].strip().rstrip(',- ')
                elif area_val.upper() in ('AMBAVADI', 'AMBAWADI'):
                    for alt in ('AMBAVADI', 'AMBAWADI'):
                        if name_val.upper().endswith(alt):
                            name_val = name_val[:len(name_val)-len(alt)].strip().rstrip(',- ')
            else:
                name_val, area_val = split_party_area(item)
            
            name_val = re.sub(r'\s*\([^)]+\)\s*$', '', name_val).strip()
            name_val = name_val.rstrip(',- /')
            
            if name_val:
                current_party = name_val
                current_area = area_val
            continue
        if is_subtotal(item) or not current_party:
            continue
        record = {
            "party_name": current_party,
            "party_location": current_area,
            "product_name": item,
        }
        for key, idx in col.items():
            if key in record or idx >= len(raw_row):
                continue
            record[key] = raw_row[idx]
        records.append(record)
    return records, detected
