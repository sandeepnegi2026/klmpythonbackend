"""
"PARTY+ITEM WISE SALE" columnar export (KAPOOR MEDICAL STORE / Marg free-issue): a flat
per-row table

    SNO | PARTY NAME | BILL NO. | BILL DATE | ITEM NAME | BATCH | SALE QUANTITY |
    FREE QTY | EXPIRY DATE | GROSS AMOUNT | NET AMOUNT | M.R.P.

whose PARTY NAME column glues the customer's town onto the firm as a trailing hyphen
segment ("AASHISH MEDICAL AGENCY MANDI  -MANDI", "CHAUDHARY MEDICOSE KULLU -KULLU",
"AMAN MEDICAL STORE  SUNDER NAGAR -MANDI").

The generic ``tabular`` reader maps every column correctly but leaves party_location empty
(the town sits inside party_name). This layout reuses tabular's exact column mapping — so
qty / amount / dates are byte-identical to what tabular already produced — and adds the one
missing piece: peel the trailing hyphen-delimited area into party_location. Title-gated on
"PARTY+ITEM WISE SALE" plus a columnar party header, so it claims only this family; every
other tabular file is untouched. Names without the "-<AREA>" suffix keep an empty location.
"""
import re

from core.header_match import map_headers

from extractors.party_xlsx.header_detect import detect_header_row
from extractors.party_xlsx.layouts.tabular import records_from_mapped
from extractors.party_xlsx.parse_common import cell_text, compact

_TITLE = "partyitemwisesale"
# Trailing "  -<AREA>" segment: whitespace, a hyphen, then an all-letters town that may
# carry internal spaces / dots ("SUNDER NAGAR", "NER CHOWK", "JOGINDER NAGAR"). Capped in
# ``_split_hyphen_area`` so a long non-area tail ("... - XYZ MEDICALS PVT LTD") never splits.
_HYPHEN_AREA_RE = re.compile(r"^(.*\S)\s+-\s*([A-Za-z][A-Za-z. ]*?)\s*$")


def _split_hyphen_area(name):
    """(party_name, party_location) splitting a trailing hyphen-delimited town, else (name, '')."""
    match = _HYPHEN_AREA_RE.match(name)
    if not match:
        return name, ""
    head, tail = match.group(1).strip(), match.group(2).strip()
    if head and 0 < len(tail) <= 20:
        return head, tail
    return name, ""


def detect(rows):
    head = compact(" ".join(" ".join(cell_text(c) for c in r) for r in rows[:8]))
    if _TITLE not in head:
        return False
    header_idx = detect_header_row(rows)
    if header_idx is None:
        return False
    keys = {info["canonical"]
            for info in map_headers([str(c) for c in rows[header_idx]], "party").values()}
    return "party_name" in keys and "product_name" in keys and bool(keys & {"amount", "qty"})


def parse_party_item_wise_sale(rows):
    header_idx = detect_header_row(rows)
    if header_idx is None:
        return [], {}
    headers = [str(h) if h else f"col_{i}" for i, h in enumerate(rows[header_idx])]
    records, detected = records_from_mapped(headers, rows, header_idx)
    # Drop the trailing "GRAND TOTALS" row: it carries a qty/amount (so records_from_mapped
    # keeps it) but no ITEM NAME. Every real sale row has a product, so a blank product here
    # is the report's own total — leaving it in doubles the extracted amount vs the printed
    # grand total. (This is exactly the AMBER TOTAL_MISMATCH the file first showed.)
    records = [r for r in records if str(r.get("product_name", "")).strip()]
    for record in records:
        if str(record.get("party_location", "")).strip():
            continue
        base, loc = _split_hyphen_area(str(record.get("party_name", "")).strip())
        if loc:
            record["party_name"] = base
            record["party_location"] = loc
    return records, detected
