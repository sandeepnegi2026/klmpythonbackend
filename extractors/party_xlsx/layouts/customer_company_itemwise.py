"""
"Customer / Company / Itemwise Sales" — MARG/KLM Excel export (MANISH MEDICAL
CORPORATION `klm partywise.xls`). The .xls twin of the party-PDF
``customer_itemwise_series`` layout: the report is banded
Location -> Series -> Customer -> Company, with product lines in real mapped columns
(Code | Item Name | Packing | Batch No. | Qty. | FQty. | Rate | Amount | Inv. No. | Inv. Date).

Two column-0 band styles must be told apart — exactly the rule the PDF layout uses:

    ABE02 -  ABEERA MEDICAL AND GENERAL STORE ,  AHMEDABAD  AHMEDABAD   <- customer/party (has a comma)
    KLM LABORA - PEDIATRIC                                              <- company/division (no comma)

The generic ``customer_product_banded`` reader treats BOTH as bare bands (their
voucher columns are blank), so the company band — which sits *last*, right above the
product line — overwrites party_name with "KLM LABORA - PEDIATRIC". This layout is
title-gated on the distinctive "Customer / Company / Itemwise Sales" header and applies
the comma rule, so party_name is the real firm and party_location its area/city.
(Division is left to product-master enrichment downstream, as before.)
"""
import re

from core.header_match import map_headers, normalize

from extractors.party_xlsx.header_detect import detect_header_row
from extractors.party_xlsx.parse_common import cell_text, is_subtotal

# Section markers / block subtotals / page furniture that head or close a block — never a
# party band and never a product line (mirrors the PDF layout's control-row filter).
_CTRL_RE = re.compile(
    r"^\s*(?:location\s*:|series\s*:|total of|grand total|customer\s*/|code\s+item|"
    r"year\s*:|page\b|contact\b)",
    re.IGNORECASE,
)
# "<code> - <rest>" band: party when <rest> has a comma ("NAME , AREA CITY"), company
# when it does not ("KLM LABORA - PEDIATRIC"). Non-greedy head so the FIRST " - " splits.
_BAND_RE = re.compile(r"^(.*?)\s-\s(.+)$")


def _ws(text):
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def detect(rows):
    # ``normalize`` turns the "Customer / Company / Itemwise Sales" title's slashes into
    # spaces, so match the de-spaced form.
    head = normalize(
        " ".join(" ".join(cell_text(c) for c in r) for r in rows[:10])
    ).replace(" ", "")
    return "customercompany" in head and "itemwisesales" in head


def parse_customer_company_itemwise(rows):
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
        record = {key: (raw[idx] if idx < len(raw) else "") for key, idx in col.items()}
        product = cell_text(record.get("product_name", ""))
        if product and not is_subtotal(product):
            # a real product line — attach the current customer band
            if current_party:
                record["party_name"] = current_party
            if current_loc and not cell_text(record.get("party_location", "")):
                record["party_location"] = current_loc
            records.append(record)
            continue

        # not a product line -> a column-0 band or a marker
        first = _ws(cell_text(raw[0]))
        if not first or _CTRL_RE.match(first):
            continue
        band = _BAND_RE.match(first)
        if not band:
            continue
        rest = band.group(2)
        if "," in rest:                                   # customer / party band
            name, area = rest.split(",", 1)
            name = name.strip()
            if len(re.findall(r"[A-Za-z]", name)) >= 3:   # ignore stray "X - Y" noise
                current_party = name
                current_loc = _ws(area.strip(" .,"))
        # else: company/division band ("KLM LABORA - PEDIATRIC") — ignored on purpose;
        #       division is stamped by product-master enrichment downstream.

    return records, detected
