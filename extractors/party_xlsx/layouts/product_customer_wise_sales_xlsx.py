"""
"Product-Customer Wise Sales" — SwilERP Excel export (CAPITAL PHARMA AGENCIES / KLM).

The Excel sibling of the PDF ``product_customer_wise_sales`` layout. Same three-level
nesting, but here the bands are single-cell rows and the customer lines are proper
four-cell rows, so no positional (x-coordinate) slicing is needed::

    Customer | Station | Qty. | Sales Value                 <- header (row of 4 cells)
    KLM PEDIA                                               <- DIVISION band (1 cell)
    KLM2.11      KLM D3 NANO DROP 15ML            15ML      <- PRODUCT band (1 cell: code name pack)
    TAPAN MEDICO | KOLKATA | 6 | 535.74                    <- customer row (4 cells)
    KANHAIYA LIFE CARE MEDICINE | KOLKATA | 3 | 267.87
    TOTAL |  | 21 | 1875.09                                <- per-product subtotal (skip)
    ...
    GRAND TOTAL |  | 541 | 112460.51                       <- grand total (skip)

Falls to the generic ``tabular`` reader otherwise: it maps the four customer columns
(Customer -> party_name, Station -> party_location, Qty/Sales Value) but never attaches
the product, which is a band, so ``product_name`` is empty -> RED.

A single-cell band is a PRODUCT if its first token is a product code (letters then a dot
or digit, e.g. ``KLM2.11`` / ``KLM119`` / ``KLM.11``); otherwise it is a DIVISION band
(``KLM PEDIA``), whose ``KLM`` company prefix is stripped to match the PDF sibling.
"""
import re

from extractors.party_xlsx.parse_common import cell_text, compact

# Compact signatures (normalize lowercases + turns every non-alphanumeric into a space,
# then compact removes the spaces — so "Qty." -> "qty" and the header glues to this).
_TITLE = "productcustomerwisesales"
_HEADER = "customerstationqtysalesvalue"
# A product code: 1-6 letters then a dot or digit (KLM2.11 / KLM119 / KLM.11 / KLM2001).
_CODE_RE = re.compile(r"^[A-Za-z]{1,6}[.\d]")
# The per-product / grand subtotal rows carry col0 EXACTLY "TOTAL" / "GRAND TOTAL" (and a blank
# Station cell). Matched exactly so a customer whose name merely starts with "total" (e.g.
# "TOTAL CARE PHARMA") is never dropped.
_SUBTOTAL_LABELS = {"total", "grand total"}


def _header_idx(rows):
    for idx, row in enumerate(rows[:15]):
        if compact(" ".join(cell_text(c) for c in row)) == _HEADER:
            return idx
    return None


def detect(rows):
    if _header_idx(rows) is None:
        return False
    head = compact(" ".join(" ".join(cell_text(c) for c in r) for r in rows[:8]))
    return _TITLE in head


def _parse_band(text):
    """A PRODUCT band 'KLM2.11  KLM D3 NANO DROP 15ML  15ML' -> (product_name, pack).
    Split on runs of 2+ spaces: [code, name, pack]; pack is the last group when present."""
    parts = re.split(r"\s{2,}", text.strip())
    if len(parts) >= 3:
        return " ".join(parts[1:-1]).strip(), parts[-1].strip()
    if len(parts) == 2:
        return parts[1].strip(), ""
    return "", ""


def parse_product_customer_wise_sales_xlsx(rows):
    header_idx = _header_idx(rows)
    if header_idx is None:
        return [], {}

    records = []
    division = ""
    product = ""
    pack = ""
    for raw in rows[header_idx + 1:]:
        cells = [cell_text(c) for c in raw]
        populated = [c for c in cells if c.strip()]
        if not populated:
            continue

        # Single-cell row -> a band (or SwilERP footer furniture).
        if len(populated) == 1:
            text = populated[0].strip()
            low = text.lower()
            if "powered by" in low or "swilerp" in low:
                continue
            if _CODE_RE.match(text.split()[0]):
                product, pack = _parse_band(text)
            else:
                division = text[4:].strip() if text[:4].upper() == "KLM " else text
            continue

        # Multi-cell row -> a customer line or a TOTAL / GRAND TOTAL subtotal.
        name = cells[0].strip()
        if not name or name.rstrip(":").strip().lower() in _SUBTOTAL_LABELS:
            continue
        station = cells[1].strip() if len(cells) > 1 else ""
        qty = cells[2].strip() if len(cells) > 2 else ""
        value = cells[3].strip() if len(cells) > 3 else ""
        if not qty and not value:
            continue
        records.append({
            "division": division,
            "party_name": name,
            "party_location": station,
            "product_name": product,
            "pack": pack,
            "qty": qty,
            "amount": value,
        })

    detected = {"Customer": "party_name", "Station": "party_location", "Qty.": "qty",
                "Sales Value": "amount", "Product": "product_name", "Division": "division"}
    return records, detected
