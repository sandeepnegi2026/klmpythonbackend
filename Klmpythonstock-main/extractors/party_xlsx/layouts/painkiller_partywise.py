import re

from core.header_match import normalize

from extractors.party_xlsx.parse_common import cell_text, split_party_area
import re

def _clean_party(name, area):
    if area.startswith("-"):
        area = area[1:].strip()
    m = re.search(r'\[\d+\]', name)
    if m:
        name = name[:m.start()]
    name = re.sub(r'^[A-Z0-9]{3,10}-', '', name)
    return name.strip(' -'), area.strip()


def parse_painkiller_partywise(rows):
    header_idx = None
    has_area = False
    for idx, row in enumerate(rows[:150]):
        cells = [normalize(c) for c in row if cell_text(c)]
        if "party" in cells and "item" in cells:
            header_idx = idx
            has_area = "area" in cells
            break
    if header_idx is None:
        return [], {}
    party_col = 0 if not has_area else 1
    item_col = 2 if not has_area else 3
    records = []
    current_party = ""
    current_area = ""
    for raw_row in rows[header_idx + 1 :]:
        area_val = cell_text(raw_row[0] if has_area and raw_row else "")
        if has_area and area_val and not cell_text(raw_row[1] if len(raw_row) > 1 else ""):
            if re.match(r"^\d{2}-", area_val):
                current_area = area_val
            continue
        party_val = cell_text(raw_row[party_col] if party_col < len(raw_row) else "")
        item_val = cell_text(raw_row[item_col] if item_col < len(raw_row) else "")
        if party_val and not item_val and "total" not in party_val.lower():
            current_party, area_from_party = split_party_area(party_val)
            current_party, area_from_party = _clean_party(current_party, area_from_party)
            if area_from_party:
                current_area = area_from_party
            continue
        if not item_val or "total" in item_val.lower() or item_val.startswith("z{{{"):
            continue
        if not current_party:
            continue
        product = re.sub(r"^\d+-", "", item_val).strip()
        records.append(
            {
                "party_name": current_party,
                "party_location": current_area,
                "product_name": product,
                "batch_no": cell_text(
                    raw_row[item_col + 4] if len(raw_row) > item_col + 4 else ""
                ),
                "invoice_number": cell_text(
                    raw_row[item_col + 6] if len(raw_row) > item_col + 6 else ""
                ),
                "invoice_date": cell_text(
                    raw_row[item_col + 7] if len(raw_row) > item_col + 7 else ""
                ),
            }
        )
    detected = {
        "Party": "party_name",
        "Item": "product_name",
        "BatchNo": "batch_no",
        "BillNo": "invoice_number",
        "BillDate": "invoice_date",
    }
    return records, detected
