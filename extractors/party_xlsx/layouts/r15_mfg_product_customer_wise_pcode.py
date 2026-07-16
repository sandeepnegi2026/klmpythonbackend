"""
"Sales Report (Mfg-Products-Customer Wise)" — an HMRS PHARMA CARE / ATLANTA export
(Cash-Counter / Sheetal group ERP) whose columns are:

    PCode | Product Name | Packing | Qty | Free | NetAmt

and whose customer sits in a **band row** in column 0 of the form:

    A-ONE CHEMIST & GENERAL STORES -:- V-M THANE-W      <- <PARTY> -:- <AREA>

i.e. the customer name is on the LEFT of the "-:-" separator (a multi-word firm name)
and the salesman/area code on the RIGHT. Each customer group is followed by TWO
sub-total rows (blank PCode + blank Product Name, only Qty/NetAmt filled): the first
repeats the AREA label, the second repeats the PARTY name.

Gate token: the compacted column-header run ``pcodeproductnamepacking`` — the leading
"PCode" column before "Product Name"/"Packing" is unique to this export. It is NOT
handled by the existing band readers:

* ``customer_product_wise_band`` requires a SPACE-FREE division code on the LEFT of
  "-:-" (KLMQ -:- PARTY) — here the left side is a multi-word party name, so it is
  skipped.
* ``partywise_band`` requires an invoice/date (voucher) column — this report has none,
  so its structural detect returns False and the file falls through to ``tabular``
  (which finds no party column -> MISSING_REQUIRED_FIELD:party_name, 0 rows).

Column mapping is exact-header positional (party-route canonicals):
    PCode -> hsn_code, Product Name -> product_name, Packing -> pack,
    Qty -> qty, Free -> free_qty, NetAmt -> net_amount.
Qty and value are kept in separate columns (no derivation). Free is always empty in
this export but is mapped to free_qty for completeness.
"""
import re

from extractors.party_xlsx.parse_common import cell_text

# Band row: "<PARTY NAME> -:- <AREA>" in column 0. The party (left) is multi-word text
# (contains a space), which is what separates it from the customer_product_wise_band
# "<space-free-code> -:- <party>" orientation.
_BAND_RE = re.compile(r"^\s*(\S.*?\S)\s*-\s*:\s*-\s*(\S.*?)\s*$")

_HEADER = ("pcode", "productname", "packing", "qty", "free", "netamt")


def _compact(text):
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def _header_idx(rows):
    for i, raw in enumerate(rows[:15]):
        cells = [_compact(cell_text(c)) for c in raw]
        if cells[:6] == list(_HEADER):
            return i
    return None


def _band_party_area(text):
    """Return (party, area) if ``text`` is a "<party> -:- <area>" band, else (None, None)."""
    m = _BAND_RE.match(text)
    if not m:
        return None, None
    left = m.group(1).strip()
    right = m.group(2).strip().rstrip("-").strip()
    # party must be a real multi-word firm name (has a space) so a bare short code
    # ("KLMQ -:- X") is left to customer_product_wise_band and never diverted here.
    if " " not in left:
        return None, None
    return left, right


def detect(rows):
    hi = _header_idx(rows)
    if hi is None:
        return False
    bands = prods = 0
    for raw in rows[hi + 1: hi + 400]:
        if not raw:
            continue
        c0 = cell_text(raw[0])
        prod = cell_text(raw[1]) if len(raw) > 1 else ""
        if not prod and " -:- " in c0:
            p, _a = _band_party_area(c0)
            if p:
                bands += 1
        elif c0.isdigit() and prod:
            prods += 1
    return bands >= 2 and prods >= 2


def parse_mfg_product_customer_wise_pcode(rows):
    hi = _header_idx(rows)
    if hi is None:
        return [], {}

    records = []
    current_party = ""
    current_area = ""
    for raw in rows[hi + 1:]:
        if not raw:
            continue
        c0 = cell_text(raw[0])
        prod = cell_text(raw[1]) if len(raw) > 1 else ""

        # Band row advances the current customer/area.
        if not prod and " -:- " in c0:
            party, area = _band_party_area(c0)
            if party:
                current_party, current_area = party, area
            continue

        # A real product line has an all-digit PCode and a non-empty Product Name.
        # Every sub-total / area / party / grand-total row has a blank Product Name
        # (and a non-numeric or blank PCode), so this is a strict item gate.
        if not (c0.isdigit() and prod):
            continue
        if not current_party:
            continue

        record = {
            "hsn_code": c0,
            "product_name": prod,
            "pack": cell_text(raw[2]) if len(raw) > 2 else "",
            "qty": cell_text(raw[3]) if len(raw) > 3 else "",
            "free_qty": cell_text(raw[4]) if len(raw) > 4 else "",
            "net_amount": cell_text(raw[5]) if len(raw) > 5 else "",
            "party_name": current_party,
        }
        if current_area:
            record["party_location"] = current_area
        records.append(record)

    detected = {
        "PCode": "hsn_code",
        "Product Name": "product_name",
        "Packing": "pack",
        "Qty": "qty",
        "Free": "free_qty",
        "NetAmt": "net_amount",
    }
    return records, detected
