"""
"Salesmen wise Report" (e.g. SAFE LIFE ENTERPRISES) — a customer-banded sale list
whose product lines carry the manufacturer/division in column 0:

    Manufacturer/Division  Area City  Product Name  PCode  Qty  Free  GrsAmt ...
    AAI MEDICAL                                                              <- customer band
    KLM COSMOCOR  MANKHURD  OFACITIX TABLET  35684   1         146.43 ...    <- product line
    AAI MEDICAL                              1         146.43                 <- per-party total

The customer heads a bare band in column 0 (no product, no qty); the lines below carry
a division in column 0, the city in column 1, the product in column 2 and the quantity
in column 4. The per-party total repeats the customer name with a qty but no product.
"""
from core.header_match import normalize

from extractors.party_xlsx.parse_common import cell_text, is_numeric_qty, is_subtotal

_TITLE = "salesmen wise"


def title_matches(rows):
    head = normalize(" ".join(" ".join(cell_text(c) for c in r) for r in rows[:6]))
    return _TITLE in head


def _find_header(rows):
    for idx, row in enumerate(rows[:15]):
        joined = normalize(" ".join(cell_text(c) for c in row))
        if "product name" in joined and ("manufacturer" in joined or "division" in joined) and "qty" in joined:
            return idx
    return None


def detect(rows):
    return title_matches(rows) and _find_header(rows) is not None


def parse_salesmen_partywise(rows):
    header_idx = _find_header(rows)
    if header_idx is None:
        return [], {}
    norm = [normalize(c) for c in rows[header_idx]]

    def col(*names):
        for n in names:
            if n in norm:
                return norm.index(n)
        return None

    area_i = col("area city", "area")
    prod_i = col("product name")
    qty_i = col("qty")
    free_i = col("free")
    amt_i = col("grsamt", "netamt", "amount")
    if prod_i is None or qty_i is None:
        return [], {}

    def at(cells, i):
        return cells[i] if (i is not None and i < len(cells)) else ""

    records = []
    current_party = ""
    for raw in rows[header_idx + 1:]:
        cells = [cell_text(c) for c in raw]
        if not any(cells):
            continue
        product = at(cells, prod_i)
        qty = at(cells, qty_i)
        first = cells[0] if cells else ""

        # product line: a product name + a numeric qty
        if product and is_numeric_qty(qty) and not is_subtotal(product):
            if not current_party:
                continue
            records.append({
                "party_name": current_party,
                "party_location": at(cells, area_i).strip().rstrip("("),
                "product_name": product,
                "qty": qty,
                "free_qty": at(cells, free_i),
                "amount": at(cells, amt_i),
            })
            continue

        # customer band: a bare name in column 0 with no product (per-party totals
        # repeat the name but carry a qty, so they are excluded by the qty check).
        if first and not product and not is_numeric_qty(qty) and not is_subtotal(first):
            current_party = first.strip()

    detected = {"Product Name": "product_name", "Area City": "party_location",
                "Qty": "qty", "Free": "free_qty", "GrsAmt": "amount"}
    return records, detected
