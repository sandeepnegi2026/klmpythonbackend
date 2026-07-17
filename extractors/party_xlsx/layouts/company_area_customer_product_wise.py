"""
"Company/Area/Customer/Product Wise Sales" — Logic-ERP Excel export (SHRI SAI / KLM).

A customer-banded party report whose party sits in a single **column-0** band row::

    PRODUCT C | PRODUCT NAME | QTY | FREE QT | GOODS VALU | PRATE | VALUE(PRATE)   <- header
    CUSTOMER NAME : APNA MEDICOS-BHADAKAMORA-BHADAKAMORA                           <- party band (col 0)
    12428 | SOFIDEW BABY LOTION 100ML | 2 | 0 | 427.12 | 192.2 | 384.4            <- product line
    GROUP TOTAL APNA MEDICOS-BHADAKAMORA-BHADAKAMORA                               <- per-party subtotal (skip)
    ...
    NET TOTAL |  | 83 | 7 | 10005.2 | 0 | 0                                        <- grand total (skip)

This shares the "Customer/Product Wise" title with the generic ``partywise_band`` reader
and so was routed there, but that reader looks for the band in the *Name*/product column
— here the band is a lone ``CUSTOMER NAME : ...`` cell in column 0 (and its ``CUSTOMER
NAME :`` prefix isn't matched by the shared band regex), so no party was ever captured and
every product line dropped -> RED party_name. Routed ahead of ``partywise_band`` and gated
on all three of: the "company area customer product wise" title, the PRODUCT-NAME/QTY/PRATE
header, and at least one ``CUSTOMER NAME :`` band — so only this exact export is diverted.

The band tail is ``NAME-AREA-CITY``; party_name is the segment before the first ``-`` and
party_location the first non-empty area/city segment after it (a lone ``.`` means blank).
GOODS VALU (whose grand total the ERP prints in NET TOTAL) maps to ``amount``; PRATE to
``rate``.
"""
import re

from core.header_match import normalize

from extractors.party_xlsx.parse_common import cell_text, is_numeric_qty

_TITLE = "company area customer product wise"
# A column-0 party band: "CUSTOMER NAME : APNA MEDICOS-BHADAKAMORA-BHADAKAMORA".
_BAND_RE = re.compile(r"^\s*customer\s+name\s*[:\-]\s*(.+)$", re.IGNORECASE)


def _header_idx(rows):
    for idx, row in enumerate(rows[:12]):
        norm = [normalize(cell_text(c)) for c in row]
        if "product name" in norm and "qty" in norm and "prate" in norm:
            return idx
    return None


def _has_band(rows):
    for raw in rows:
        if raw and _BAND_RE.match(cell_text(raw[0]) if raw else ""):
            return True
    return False


def detect(rows):
    if _header_idx(rows) is None:
        return False
    head = normalize(" ".join(" ".join(cell_text(c) for c in r) for r in rows[:8]))
    return _TITLE in head and _has_band(rows)


def _split_party(text):
    """Band tail 'NAME-AREA-CITY' -> (party_name, party_location). Name is the first
    hyphen segment; location is the first non-empty segment after it (a bare '.' = blank)."""
    parts = [re.sub(r"\s+", " ", p).strip() for p in text.split("-")]
    name = parts[0]
    location = next((p for p in parts[1:] if p and p != "."), "")
    return name, location


def parse_company_area_customer_product_wise(rows):
    header_idx = _header_idx(rows)
    if header_idx is None:
        return [], {}
    norm = [normalize(cell_text(c)) for c in rows[header_idx]]

    def col(name):
        return norm.index(name) if name in norm else None

    prod_i = col("product name")
    qty_i = col("qty")
    free_i = col("free qt")
    amt_i = col("goods valu")
    rate_i = col("prate")

    def at(cells, i):
        return cells[i].strip() if (i is not None and i < len(cells)) else ""

    records = []
    party = ""
    location = ""
    for raw in rows[header_idx + 1:]:
        cells = [cell_text(c) for c in raw]
        if not any(c.strip() for c in cells):
            continue
        first = cells[0].strip()
        band = _BAND_RE.match(first)
        if band:
            party, location = _split_party(band.group(1))
            continue
        upper = first.upper()
        if upper.startswith("GROUP TOTAL") or upper.startswith("NET TOTAL"):
            continue
        product = at(cells, prod_i)
        qty = at(cells, qty_i)
        # A real product line carries a product name and a numeric qty. The repeated header
        # ("PRODUCT NAME"/"QTY") and the page-break furniture ("Company Name:" etc.) fail this.
        if not product or not is_numeric_qty(qty):
            continue
        if not party:
            continue
        records.append({
            "party_name": party,
            "party_location": location,
            "product_name": product,
            "qty": qty,
            "free_qty": at(cells, free_i),
            "rate": at(cells, rate_i),
            "amount": at(cells, amt_i),
        })

    detected = {"CUSTOMER NAME": "party_name", "PRODUCT NAME": "product_name", "QTY": "qty",
                "FREE QT": "free_qty", "GOODS VALU": "amount", "PRATE": "rate"}
    return records, detected
