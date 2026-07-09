from core.header_match import normalize

from extractors.party_xlsx.parse_common import (
    cell_text,
    is_subtotal,
    looks_like_date,
)


def parse_data_spec_sale_by_item(rows):
    header_idx = None
    for idx, row in enumerate(rows[:150]):
        cells = [normalize(c) for c in row if cell_text(c)]
        if "item name" in cells and "amount" in cells:
            header_idx = idx
            break
    if header_idx is None:
        return [], {}
    records = []
    current_product = ""
    for raw_row in rows[header_idx + 1 :]:
        sr = cell_text(raw_row[0] if raw_row else "")
        item = cell_text(raw_row[3] if len(raw_row) > 3 else "")
        if not item:
            continue
        if is_subtotal(item):
            continue
        if sr.isdigit() and not looks_like_date(
            cell_text(raw_row[1] if len(raw_row) > 1 else "")
        ):
            current_product = item
            continue
        if not sr or "." not in sr or not current_product:
            continue
        if not item.startswith(">>"):
            continue
        party_raw = item.lstrip(">").strip()
        party_name = party_raw.split("{")[0].strip()
        party_area = ""
        if "{" in party_raw and "}" in party_raw:
            party_area = party_raw.split("{", 1)[1].split("}", 1)[0].strip()
        records.append(
            {
                "party_name": party_name,
                "party_location": party_area,
                "product_name": current_product,
                "invoice_date": cell_text(raw_row[1] if len(raw_row) > 1 else ""),
                "invoice_number": cell_text(raw_row[2] if len(raw_row) > 2 else ""),
                "qty": cell_text(raw_row[4] if len(raw_row) > 4 else ""),
                "free_qty": cell_text(raw_row[5] if len(raw_row) > 5 else ""),
                "amount": cell_text(raw_row[9] if len(raw_row) > 9 else ""),
            }
        )
    detected = {
        "Item Name": "product_name",
        "DocNo": "invoice_number",
        "Date": "invoice_date",
        "Qty": "qty",
        "Free": "free_qty",
        "Amount": "amount",
    }
    return records, detected
