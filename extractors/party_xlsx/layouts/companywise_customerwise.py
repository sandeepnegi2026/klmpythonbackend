"""
"Companywise Customerwise Report" — a wide, sparsely-populated Logic-ERP export
(e.g. MINERVA STORES) where columns are spread far apart:

    Company:        362   KLM -COSMO                        <- company/division marker
                                              BAGEPALLI     <- area/city band (late column)
    ASHWINI MEDICALS GEN STORES   18031        9483088952   <- customer band (early column)
       362135  EKRAN AQUA GEL          1     0      277.97  <- product line (qty + value)
                                                    277.97  <- per-customer subtotal (value only)

The customer heads a band in an early column; its product lines (with a Sale Qty)
follow; a city sits in a far-right band. The generic reader sees no party column, so
this layout carries the current customer (and city) down onto each product line.
"""
from core.header_match import normalize

from extractors.party_xlsx.parse_common import cell_text, is_numeric_qty, is_subtotal

_TITLE = "companywise customerwise"


def title_matches(rows):
    head = normalize(" ".join(" ".join(cell_text(c) for c in r) for r in rows[:6]))
    return _TITLE in head


def _find_header(rows):
    for idx, row in enumerate(rows[:15]):
        joined = normalize(" ".join(cell_text(c) for c in row))
        if "sale qty" in joined:
            return idx
    return None


def detect(rows):
    return title_matches(rows) and _find_header(rows) is not None


def _is_word(text, minlen=4):
    import re
    return bool(re.search(r"[A-Za-z]{%d,}" % minlen, text)) and not is_numeric_qty(text)


def parse_companywise_customerwise(rows):
    header_idx = _find_header(rows)
    if header_idx is None:
        return [], {}
    hrow = [normalize(c) for c in rows[header_idx]]

    def hcol(name):
        for i, h in enumerate(hrow):
            if name in h:
                return i
        return None

    qty_i = hcol("sale qty")
    free_i = hcol("sch")
    val_i = hcol("sal val") or hcol("value")
    if qty_i is None:
        return [], {}

    records = []
    current_party = ""
    current_area = ""
    for raw in rows[header_idx + 1:]:
        cells = [cell_text(c) for c in raw]
        if not any(cells):
            continue
        low = " ".join(cells).lower()
        if low.strip().startswith("company") or "company:" in low:
            continue
        qty = cells[qty_i] if qty_i < len(cells) else ""

        # product line: a numeric Sale Qty
        if is_numeric_qty(qty):
            # product name = the worded cell sitting left of the quantity columns
            name = ""
            for j in range(qty_i - 1, -1, -1):
                if j < len(cells) and _is_word(cells[j], 3):
                    name = cells[j]
                    break
            if not name or is_subtotal(name) or not current_party:
                continue
            records.append({
                "party_name": current_party,
                "party_location": current_area,
                "product_name": name,
                "qty": qty,
                "free_qty": cells[free_i] if (free_i is not None and free_i < len(cells)) else "",
                "amount": cells[val_i] if (val_i is not None and val_i < len(cells)) else "",
            })
            continue

        # band row (qty empty): a customer name in an early column, or a city far right
        early = [(j, cells[j]) for j in range(0, min(len(cells), 12)) if _is_word(cells[j])]
        late = [(j, cells[j]) for j in range(25, len(cells)) if _is_word(cells[j])]
        if early:
            current_party = early[0][1].strip().strip(",")
        elif late:
            current_area = late[0][1].strip().strip(",")

    detected = {"Customer": "party_name", "Item": "product_name",
                "Sale Qty": "qty", "Sch.Qty.": "free_qty", "Sal Val": "amount"}
    return records, detected
