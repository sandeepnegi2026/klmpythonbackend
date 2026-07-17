"""
"Customer + Product Wise Sale (Detail)" — a KLM multi-division sales export (seen from
AMI DERMATOLOGY) whose product columns map cleanly:

    Inv No | InvDate | Product Name | Packing | Qty | Free | MRP | Rate | PTR | PTS |
    CD% | NetAmt | Area | IGST% | IGSTAmt | CGST/CST% | CGST/CSTAmt | GrsAmt

but whose party sits in a *band row* in column 0 of the form:

    KLMQ -:- VARDHAMAN MEDICO           <- <division-code> -:- <party name>

i.e. the short division code is on the LEFT of the "-:-" separator and the customer on
the RIGHT — the REVERSE of the JALARAM ``partywise_band`` band, which is ``PARTY -:- AREA``
(party on the left). The band carries down onto every product line until the next band.

Rows that must be skipped:
  * division sub-totals   ``KLMQ  | | | | 1072 | ...``  (a bare code, no "-:-", no product)
  * per-party sub-totals  ``AADI MEDICAL ...  | | | | 30 | ...`` (party repeated, product blank)
  * ``GRAND TOTAL`` / ``(Report End)`` / prepared-by footer lines

The generic ``partywise_band`` reader looks for the band in the Name/Product column and
splits "-:-" the JALARAM way (party-first), so it never attaches ``party_name`` here
(-> MISSING_REQUIRED_FIELD:party_name). This layout reads the band from column 0 with the
division-code-first orientation and leaves every other (already-mapped) column untouched.
"""
import re

from core.header_match import map_headers

from extractors.party_xlsx.header_detect import detect_header_row
from extractors.party_xlsx.parse_common import cell_text

# Band row: "<CODE> -:- <PARTY NAME>" in column 0. The left side is a SHORT, space-free
# division code (KLMQ, KLMP, KLMCO, KLMPD, KLABOR, KL(COS, ...). Requiring the left token
# to be space-free is what separates this from JALARAM's "FULL PARTY NAME -:- AREA" band
# (whose left side is a multi-word party name).
_BAND_RE = re.compile(r"^\s*([A-Z0-9()][A-Z0-9()./]{1,11})\s*-\s*:\s*-\s*(\S.*?)\s*$")


def _columns(rows, header_idx):
    headers = [str(h) if cell_text(h) else f"col_{i}" for i, h in enumerate(rows[header_idx])]
    detected = {raw: info["canonical"] for raw, info in map_headers(headers, "party").items()}
    col = {}
    for idx, raw in enumerate(headers):
        key = detected.get(raw)
        if key and key not in col:
            col[key] = idx
    return headers, col


def _band_party(text):
    """Return (division_code, party_name) if ``text`` is a band row, else (None, None)."""
    m = _BAND_RE.match(text)
    if not m:
        return None, None
    return m.group(1).strip(), m.group(2).strip().rstrip("-").strip()


def detect(rows):
    header_idx = detect_header_row(rows, min_matches=4)
    if header_idx is None:
        return False
    _headers, col = _columns(rows, header_idx)
    # Band-based (no party column of its own); needs product + qty to be a line-item table.
    if "party_name" in col:
        return False
    if "product_name" not in col or "qty" not in col:
        return False
    # Require BOTH an invoice column and an Area (party_location) column. JALARAM's
    # reverse-orientation "PARTY -:- AREA" band has neither, so this structural gate plus
    # the space-free left-code band pattern cannot divert it (or any plain columnar file).
    if "invoice_number" not in col or "party_location" not in col:
        return False
    prod_idx = col["product_name"]
    bands = prods = 0
    for raw in rows[header_idx + 1: header_idx + 400]:
        if not raw:
            continue
        c0 = cell_text(raw[0])
        prod = cell_text(raw[prod_idx]) if prod_idx < len(raw) else ""
        if not prod and _BAND_RE.match(c0):
            bands += 1
        elif prod:
            prods += 1
    return bands >= 2 and prods >= 2


def parse_customer_product_wise_band(rows):
    header_idx = detect_header_row(rows, min_matches=4)
    if header_idx is None:
        return [], {}
    headers, col = _columns(rows, header_idx)
    prod_idx = col.get("product_name")

    records = []
    current_party = ""
    current_div = ""
    for raw in rows[header_idx + 1:]:
        if not raw:
            continue
        c0 = cell_text(raw[0])
        prod = cell_text(raw[prod_idx]) if (prod_idx is not None and prod_idx < len(raw)) else ""

        # A blank product column means this is not a line item: it is a band
        # ("<code> -:- <party>"), a party/division sub-total (party or code repeated,
        # numbers filled), the GRAND TOTAL, or a footer. Only a band advances the party.
        if not prod:
            div, party = _band_party(c0)
            if party:
                current_div, current_party = div, party
            continue

        # Product line. Every total/sub-total in this layout has the product column blank
        # (handled above), so a non-empty product is always a real item — do NOT filter on
        # the product text (genuine items include the brand "EXTEND TOTAL").
        if not current_party:
            continue
        record = {key: (raw[idx] if idx < len(raw) else "") for key, idx in col.items()}
        record["party_name"] = current_party
        if current_div:
            record["division"] = current_div
        records.append(record)

    detected = {}
    for idx, h in enumerate(headers):
        for key, cidx in col.items():
            if cidx == idx:
                detected[h] = key
    return records, detected
