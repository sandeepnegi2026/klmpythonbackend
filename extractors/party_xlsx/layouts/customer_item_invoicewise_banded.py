"""
Customer-Item-Invoice-Wise party-wise Excel report (KLM / SANTOSH ENTERPRISES).

Structure (title cell "Customer Item - Invoice Wise"):

    Date | Trn.No | Code | Item Name | Pack | Batch | Qty | Free | ... | Value | ...
    CUSTOMER :    A.R. MEDICOSE MM       CITY : CHANDIGARH     <- band (merged cell)
    13-May-26  SB/2306  ...  ZYDIP-C CREAM  20 GM  BD601  2 ...  <- item lines
    CUSTOMER TOTAL :  ...                                        <- per-party subtotal
    ...
    GRAND TOTAL :  1341 ...  319329.35 ...                       <- grand total

This is structurally the SAME as ``customer_product_banded`` (customer as a band
header, product/sale columns beneath, per-party subtotals), so the column mapping,
product-line skipping and per-band carry-down are copied from it. It differs in TWO
ways that make ``customer_product_banded`` unusable directly:

  1. The CUSTOMER band is written into EVERY column of the row (an unmerged merged
     cell), so ``customer_product_banded``'s ``_is_merged_furniture`` guard eats it
     as a footer/banner before its band check ever runs -> party_name is never set.
     Here we test the CUSTOMER band FIRST, before any furniture guard.
  2. The band carries an optional leading customer CODE and a trailing
     ``CITY : <city>`` suffix ("CUSTOMER : 36000A0013   ANAND CHEMISTS 37  CITY :
     CHANDIGARH"). We peel the code and the CITY suffix so party_name is the firm
     name and party_location the city.

Row extraction (qty / value) is otherwise identical to ``customer_product_banded``
and reconciles exactly to the printed GRAND TOTAL.
"""
import re

from core.header_match import map_headers

from extractors.party_xlsx.constants import CUSTOMER_BAND_RE
from extractors.party_xlsx.header_detect import detect_header_row
from extractors.party_xlsx.parse_common import cell_text, compact, is_subtotal

# Distinctive title token for this export ("Customer Item - Invoice Wise").
_TITLE_TOKEN = "customeriteminvoicewise"

# A CUSTOMER band tail: optional leading numeric/alnum customer code, the firm name
# (a trailing sequence number may follow), then a "CITY : <city>" suffix.
#   "   A.R. MEDICOSE MM       CITY : CHANDIGARH"
#   " 36000A0013   ANAND CHEMISTS 37       CITY : CHANDIGARH"
_CITY_SUFFIX_RE = re.compile(r"\s*CITY\s*[:\-]\s*(.+?)\s*$", re.IGNORECASE)
# A leading customer code is a run of digits/uppercase-alnum (>=4 chars, at least one
# digit) followed by 2+ spaces before the firm name. Requiring the multi-space gap and
# an embedded digit keeps a firm name whose first word is short/all-letters ("A.R.
# MEDICOSE") from being mistaken for a code.
_LEAD_CODE_RE = re.compile(r"^\s*([0-9A-Z]{4,})\s{2,}(?=\S)")


def detect(rows):
    blob = compact(" ".join(" ".join(cell_text(c) for c in r) for r in rows[:8]))
    if _TITLE_TOKEN not in blob:
        return False
    # Require the banded shape: at least one "CUSTOMER : ..." band row.
    for row in rows[:200]:
        if row and CUSTOMER_BAND_RE.match(cell_text(row[0]) if row else ""):
            return True
    return False


def _split_band(tail):
    """(party_name, city) from a CUSTOMER band tail. City may be ''."""
    city = ""
    m = _CITY_SUFFIX_RE.search(tail)
    if m:
        city = m.group(1).strip()
        tail = tail[: m.start()]
    # Peel a leading customer code ("36000A0013   ANAND CHEMISTS 37").
    code_m = _LEAD_CODE_RE.match(tail)
    if code_m:
        tail = tail[code_m.end():]
    name = tail.strip()
    # Drop a trailing bare sequence number the ERP appends to the firm ("... 37").
    name = re.sub(r"\s+\d{1,4}$", "", name).strip()
    return name, city


def parse_customer_item_invoicewise_banded(rows):
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
    for raw in rows[header_idx + 1:]:
        if not raw:
            continue
        first = cell_text(raw[0])

        # Band check FIRST (before any furniture heuristic) — the band is written into
        # every column, so a "merged furniture" guard would otherwise eat it.
        band = CUSTOMER_BAND_RE.match(first)
        if band:
            name, city = _split_band(band.group(1))
            if name:
                current_party = name
                current_loc = city
            continue

        record = {key: (raw[idx] if idx < len(raw) else "") for key, idx in col.items()}
        product = cell_text(record.get("product_name", ""))
        # Skip blanks, subtotals ("CUSTOMER TOTAL :", "GRAND TOTAL :"), pure separators.
        if not product or is_subtotal(product) or not re.search(r"[A-Za-z0-9]", product):
            continue
        # A real sale line always carries qty/value; when both are blank it is a footer.
        value_cols = [k for k in ("qty", "amount") if k in col]
        if value_cols and all(not cell_text(record.get(k, "")) for k in value_cols):
            continue
        if current_party:
            record["party_name"] = current_party
        if current_loc and not cell_text(record.get("party_location", "")):
            record["party_location"] = current_loc
        records.append(record)

    return records, detected
