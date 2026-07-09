"""
"Customer & Items New" — UNITED MEDICAL STORES Excel export (DEEPAA/KLM division,
``cos.xlsx`` / ``jagan.xlsx`` / ``moha.xlsx`` / ``mou.xlsx`` / ``raj.xlsx`` /
``rajesh.xlsx`` / ``rame.xlsx``). A banded party-wise report whose product lines sit
in real mapped columns:

    Inv No | Inv Date | Item Name | Packing | BatchNo | Qty | Free | PurPrice | SaleValue | FreeValue

The customer sits in a col-0 *band* row glued into one cell, name and area both in it:

    Customer Name: MANASA MEDICAL AND GENERAL STORES             Area: RAJAM

Two independent blockers stop the generic readers from attaching the party:

  1. The shared ``CUSTOMER_BAND_RE`` accepts "customer:" / "party name:" but NOT
     "Customer Name:" (the word "Name" sits between "Customer" and the colon), so the
     band never matches and 0 bands are counted.
  2. The band text lives IN col-0, which maps to ``invoice_number`` ("Inv No"). The
     bare-band fallback tests "all voucher columns empty" — but the band text is IN a
     voucher column, so no row is ever voucher-empty and detect falls through to
     ``tabular`` (which has no party column). party_name is never attached.

This dedicated layout is title-gated on the compact "Customer & Items New" token PLUS
the presence of a genuine "Customer Name: … Area:" band cell, so it claims ONLY these 7
files (proven across the 215-file New_Data Excel corpus — zero theft). It reuses
``map_headers('party')`` for the product columns and applies an explicit ``Area:`` split
(the name+area are glued in ONE cell, so ``split_party_area`` cannot be used). Per-party
Qty/Free subtotal rows and the grand-total footer carry no Item Name and are skipped.
"""
import re

from core.header_match import map_headers

from extractors.party_xlsx.header_detect import detect_header_row
from extractors.party_xlsx.parse_common import cell_text, compact, is_subtotal

# Col-0 customer band: "Customer Name: <party>   Area: <town>" glued into one cell.
# Broader than the shared CUSTOMER_BAND_RE (which rejects the "Name" between
# "Customer" and the colon).
_BAND_RE = re.compile(r"^\s*customer\s*name\s*[:\-]\s*(.+)$", re.IGNORECASE)
# The literal "Area:" separator inside the band cell (case-insensitive: some cells use
# "Area: day&night junction").
_AREA_SPLIT_RE = re.compile(r"\bArea\s*[:\-]", re.IGNORECASE)


def _ws(text):
    return re.sub(r"\s+", " ", str(text).replace("\xa0", " ")).strip()


def _is_band(cell):
    return bool(_BAND_RE.match(_ws(cell)))


def detect(rows):
    # Gate 1: the compact "Customer & Items New" title token from row 1.
    head = compact(" ".join(" ".join(cell_text(c) for c in r) for r in rows[:8]))
    if "customeritemsnew" not in head:
        return False
    # Gate 2: at least one genuine "Customer Name: … Area:" band cell in col 0.
    for row in rows[:400]:
        if not row:
            continue
        first = _ws(row[0])
        if _BAND_RE.match(first) and _AREA_SPLIT_RE.search(first):
            return True
    return False


def _split_band(cell):
    """Return (party_name, party_location) from a 'Customer Name: … Area: …' cell."""
    m = _BAND_RE.match(_ws(cell))
    if not m:
        return "", ""
    rest = m.group(1)
    parts = _AREA_SPLIT_RE.split(rest, maxsplit=1)
    if len(parts) == 2:
        return _ws(parts[0]), _ws(parts[1])
    return _ws(rest), ""


def parse_customer_items_new_xlsx(rows):
    header_idx = detect_header_row(rows, min_matches=4)
    if header_idx is None:
        return [], {}

    headers = [str(h) if cell_text(h) else f"col_{i}" for i, h in enumerate(rows[header_idx])]
    header_map = map_headers(headers, "party")
    detected = {raw: info["canonical"] for raw, info in header_map.items()}

    col = {}
    for idx, raw in enumerate(headers):
        key = detected.get(raw)
        if key and key not in col:
            col[key] = idx

    records = []
    current_party = ""
    current_loc = ""
    for raw in rows[header_idx + 1 :]:
        if not raw:
            continue
        first = _ws(raw[0])

        # A col-0 customer band -> update the carried-down party / location.
        if _is_band(first):
            name, loc = _split_band(first)
            if name:
                current_party = name
                current_loc = loc
            continue

        record = {key: (raw[idx] if idx < len(raw) else "") for key, idx in col.items()}
        product = cell_text(record.get("product_name", ""))
        # Skip everything without a real Item Name: this drops the per-party Qty/Free
        # subtotal rows (col0 + product blank) and the grand-total footer.
        if not product or is_subtotal(product):
            continue

        if current_party:
            record["party_name"] = current_party
        if current_loc and not cell_text(record.get("party_location", "")):
            record["party_location"] = current_loc
        records.append(record)

    return records, detected
