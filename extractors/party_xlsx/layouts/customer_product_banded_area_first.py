"""
"Customer + Product Wise Sale (Summary)" — NAVNEET ENTERPRISES banded party_xlsx
export (KLM divisions). Same banded shape as ``customer_product_banded_grsamt`` but
an ``Area``-first column order and no ``City`` suffix:

    Report : Customer + Product Wise Sale (Summary)
    Area | Product Name | Qty | Free | GrsAmt        <- header (row 5)
    AAI MEDICAL & GENERAL STORES                      <- PARTY band (col0 name, rest blank)
    BELAPUR | KENZ SOAP | 1 |  | 122.71               <- product line: Area | Product | Qty | Free | GrsAmt
    AAI MEDICAL & GENERAL STORES |  | 2 |  | 294.14   <- PARTY SUBTOTAL (col0 repeats party, has numbers) -> skip

The band supplies party_name; product lines carry Area in col0 and the product in col1.
The generic ``tabular`` / ``partywise_band`` readers can't bind the banded party, so every
row lands with an empty party_name (RED). This reader carries the band down and skips the
per-party subtotals so summed GrsAmt reconciles to the report's own totals.
"""
from core.header_match import normalize
from extractors.party_xlsx.parse_common import cell_text, is_subtotal


def _compact(value):
    return normalize(value).replace(" ", "")


def _header_idx(rows):
    """Row of the ``Area | Product Name | Qty | Free | GrsAmt`` header. Requires the
    Area-FIRST banded signature (``area`` as the first cell, ``grsamt`` present, a
    product column) and NOT ``area city`` — that keeps the G.S. ``customer_product_
    banded_grsamt`` sibling (Product-first, 'Area City') on its own reader."""
    for idx, row in enumerate(rows[:30]):
        cells = [cell_text(c) for c in row]
        toks = [_compact(c) for c in cells if c]
        if not toks:
            continue
        tokset = set(toks)
        if (
            toks[0] == "area"
            and "productname" in tokset
            and "grsamt" in tokset
            and "areacity" not in tokset
        ):
            return idx
    return None


def detect(rows):
    return _header_idx(rows) is not None


def _to_float(value):
    text = cell_text(value).replace(",", "")
    try:
        return float(text) if text else None
    except ValueError:
        return None


def parse_customer_product_banded_area_first(rows):
    header_idx = _header_idx(rows)
    if header_idx is None:
        return [], {}

    records = []
    current_party = ""
    for raw in rows[header_idx + 1 :]:
        cells = [cell_text(c) for c in raw]
        area = cells[0].strip() if cells else ""
        product = cells[1].strip() if len(cells) > 1 else ""
        qty = cells[2] if len(cells) > 2 else ""
        free = cells[3] if len(cells) > 3 else ""
        amount = cells[4] if len(cells) > 4 else ""
        has_numbers = bool(str(qty).strip() or str(amount).strip())

        low = area.lower()
        if low.startswith(("grand total", "(report end", "prepared by", "***")):
            break

        # PARTY band: col0 has a name, no product, no numbers.
        if area and not product and not has_numbers:
            if is_subtotal(area):
                continue
            current_party = area
            continue

        # PARTY subtotal: col0 repeats the party (no product) but carries totals -> skip.
        if area and not product and has_numbers:
            continue

        # Product line: Area in col0, product in col1.
        if not product or not has_numbers or not current_party:
            continue

        record = {
            "party_name": current_party,
            "product_name": product,
            "qty": qty,
            "free_qty": free,
            "amount": amount,
            "taxable_value": amount,
        }
        if area:
            record["party_location"] = area
        amt_f, qty_f = _to_float(amount), _to_float(qty)
        if amt_f is not None and qty_f:
            record["rate"] = round(amt_f / qty_f, 4)
        records.append(record)

    detected = {
        "Area": "party_location",
        "Product Name": "product_name",
        "Qty": "qty",
        "Free": "free_qty",
        "GrsAmt": "amount",
    }
    return records, detected
