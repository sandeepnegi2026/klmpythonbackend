from core.header_match import normalize

from extractors.party_xlsx.parse_common import cell_text, is_numeric_qty, split_party_area


def parse_fawin_partywise(rows):
    header_idx = None
    # Column positions read from the *unfiltered* header row so both arrangements that
    # share the "PARTYWISE OUTWARD" banner extract: SWASTIK-style (ITEM NAME@4, with
    # INV.NO/TYPE/BATCH/EXP columns and RATE/AMOUNT at 10/11) and RAJAT-style (ITEM
    # NAME@1, no batch, RATE/AMOUNT at 8/9). Qty stays at the fixed data column 6, which
    # holds across both even where the header cell is one to the left.
    item_idx, free_idx, batch_idx, rate_idx, amount_idx = 4, 7, None, None, None
    for idx, row in enumerate(rows[:150]):
        cells = [normalize(c) for c in row if cell_text(c)]
        if "item name" in cells and "qty" in cells:
            header_idx = idx
            full = [normalize(c) for c in row]

            def _col(name, default):
                return full.index(name) if name in full else default

            item_idx = _col("item name", 4)
            free_idx = _col("free", 7)
            batch_idx = _col("batch", None)
            rate_idx = _col("rate", None)
            amount_idx = _col("amount", None)
            break
    if header_idx is None:
        return [], {}

    def _at(raw_row, idx):
        return cell_text(raw_row[idx]) if (idx is not None and len(raw_row) > idx) else ""

    records = []
    current_party = ""
    for raw_row in rows[header_idx + 1 :]:
        c0 = cell_text(raw_row[0] if raw_row else "")
        c1 = cell_text(raw_row[1] if len(raw_row) > 1 else "")
        if c0.lower().startswith("party"):
            current_party = c1 or c0.split(":", 1)[-1].strip()
            continue
        if "partywise total" in " ".join(cell_text(c) for c in raw_row).lower():
            continue
        product = cell_text(raw_row[item_idx] if len(raw_row) > item_idx else "")
        qty = cell_text(raw_row[6] if len(raw_row) > 6 else "")
        if not product or not is_numeric_qty(qty) or not current_party:
            continue
        party_name, party_area = split_party_area(current_party)
        records.append(
            {
                "party_name": party_name,
                "party_location": party_area,
                "product_name": product,
                "invoice_number": cell_text(raw_row[1] if len(raw_row) > 1 else ""),
                "invoice_date": c0,
                "qty": qty,
                "free_qty": _at(raw_row, free_idx),
                "batch_no": _at(raw_row, batch_idx),
                "rate": _at(raw_row, rate_idx),
                "amount": _at(raw_row, amount_idx),
            }
        )
    detected = {
        "ITEM NAME": "product_name",
        "QTY": "qty",
        "FREE": "free_qty",
        "BATCH": "batch_no",
        "RATE": "rate",
        "AMOUNT": "amount",
        "INV. NO.": "invoice_number",
        "DATE": "invoice_date",
    }
    return records, detected
