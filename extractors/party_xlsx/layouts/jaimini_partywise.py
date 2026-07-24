from core.header_match import normalize

from extractors.party_xlsx.parse_common import (
    cell_text,
    is_numeric_qty,
    is_subtotal,
    split_party_area,
)


def parse_jaimini_partywise(rows):
    header_idx = None
    for idx, row in enumerate(rows[:150]):
        cells = [normalize(c) for c in row if cell_text(c)]
        if "product name" in cells and "amount" in cells:
            header_idx = idx
            break
    if header_idx is None:
        return [], {}
    records = []
    current_party = ""
    for raw_row in rows[header_idx + 1 :]:
        product = cell_text(raw_row[0] if raw_row else "")
        if not product:
            continue
        if is_subtotal(product):
            continue
        qty = cell_text(raw_row[3] if len(raw_row) > 3 else "")
        if not is_numeric_qty(qty.replace(",", "")):
            current_party = (
                product.rstrip("[]").split("[")[0].strip() if product else product
            )
            continue
        if not current_party:
            continue
        party_name, party_area = split_party_area(current_party)
        records.append(
            {
                "party_name": party_name,
                "party_location": party_area,
                "product_name": product,
                "free_qty": cell_text(raw_row[1] if len(raw_row) > 1 else ""),
                "qty": qty,
                "amount": cell_text(raw_row[5] if len(raw_row) > 5 else ""),
            }
        )
    detected = {
        "Product Name": "product_name",
        "Free Qty": "free_qty",
        "Qty": "qty",
        "Amount": "amount",
    }
    return records, detected
