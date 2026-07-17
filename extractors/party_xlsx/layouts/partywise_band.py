"""
Party-as-band reports where the customer heads a group of product lines and the
columns differ enough from the ``customer_product_banded`` family to need their own
handling. Several distinct ERP exports share the shape "party band row, then its
product lines, then a per-party total":

* AW_KANARA  — ``Name | Product | Packin | Qty | Free | Value``; the party sits in
  the ``Name`` column on the first product line of each group (``INARA MEDICALS
  [ ID 85908``), blank thereafter, with ``Company :`` / ``Area :`` marker rows.
* KLM2_PATEL — ``Name | Pack | Bill Ref | Date | ... | Qty | ... | Amount``; the
  party is a bare row whose Bill Ref/Date are blank, products share the ``Name``
  column (so there is no separate product column).
* RAMAKRISHNA — ``Code | Name | Packing | Date | Bill No. | ... | Qty | ...``; the
  party is a ``code  name  address`` band whose Date/Qty are blank.
* JALARAM    — ``Product Name | Packing | Qty | Free | GrsAmt``; the party band is
  ``PARTY -:- AREA`` in column 0 with no quantity.
* SHREE_NATH — ``Bill No | Date | Product Name | Qty | ... | Amount``; the party
  band name sits in the *Product Name* column with Bill No/Date blank.

The unifying rule: a **band row** is one whose transactional columns (invoice no /
date / qty) are empty while a name column carries text and the row is not a total;
its name becomes ``party_name`` for every product line below until the next band.
Detection is gated on the specific report titles (or, for the title-less exports,
on the presence of these bands) so no currently-extracting file is diverted.
"""
import re

from core.header_match import map_headers, normalize

from extractors.party_xlsx.header_detect import detect_header_row
from extractors.party_xlsx.parse_common import cell_text, is_numeric_qty, is_subtotal

# Title strings (already in normalize() form: lower-case, alphanumerics only) that
# uniquely mark the banded exports handled here. RAMAKRISHNA's "area/party/billwise"
# is deliberately excluded — its code+name+address layout needs bespoke handling and
# the generic band reader mis-aligns it.
_TITLE_SIGNALS = (
    "areawise partywise",
    "customer product wise",
)
# Rows that introduce a section but are NOT a party (skip without emitting/banding).
_MARKER_RE = re.compile(r"^\s*(company|area|mfgr|division|page)\s*[:\-]", re.IGNORECASE)
_TOTAL_RE = re.compile(r"\b(party total|cus\.?\s*total|customer total|grand total|sub\s*total|total)\b", re.IGNORECASE)
# Strip a trailing "[ ID 85908" / "(9001305997)" / "  -:-  AREA" from a band name.
_ID_SUFFIX_RE = re.compile(r"\s*[\[\(]\s*id\b.*$", re.IGNORECASE)
_PAREN_PHONE_RE = re.compile(r"\s*\(\s*\d[\d\s\-]*\)?\s*$")
_DASH_AREA_RE = re.compile(r"\s*-\s*:\s*-\s*.*$")


def _clean_party(text):
    text = _ID_SUFFIX_RE.sub("", text)
    text = _DASH_AREA_RE.sub("", text)
    # keep only the firm name when a trailing ",city,city" address tail is present
    if "," in text:
        text = text.split(",")[0]
    text = _PAREN_PHONE_RE.sub("", text)
    return text.strip().strip(",").strip()


def _band_area(text):
    m = re.search(r"-\s*:\s*-\s*(.+)$", text)
    return m.group(1).strip() if m else ""


def title_matches(rows):
    head = normalize(" ".join(" ".join(cell_text(c) for c in r) for r in rows[:8]))
    return any(sig in head for sig in _TITLE_SIGNALS)


def _columns(rows, header_idx):
    headers = [str(h) if cell_text(h) else f"col_{i}" for i, h in enumerate(rows[header_idx])]
    detected = {raw: info["canonical"] for raw, info in map_headers(headers, "party").items()}
    col = {}
    for idx, raw in enumerate(headers):
        key = detected.get(raw)
        if key and key not in col:
            col[key] = idx
    # SHREE NATH "Qty | Qty.Fr. | Sch.Qty" exports: the mapper hands free_qty to the
    # exact synonym "Sch.Qty" (scheme allocation, all zeros there) while the REAL free
    # column "Qty.Fr." loses the race (its best fuzzy hit is the already-taken qty) and
    # is discarded as a raw_* passthrough. When BOTH headers are present, the literal
    # free column outranks the scheme column. Gated on the exact normalized header pair,
    # so no other partywise_band export changes.
    fq_idx = col.get("free_qty")
    if fq_idx is not None:
        norm_hdrs = [normalize(h) for h in headers]
        if norm_hdrs[fq_idx] == "sch qty" and "qty fr" in norm_hdrs:
            col["free_qty"] = norm_hdrs.index("qty fr")
            col.pop("raw_qty_fr", None)
    return headers, col


def detect(rows):
    """True if this is one of the party-band layouts handled here.

    Title-gated for AW_KANARA / JALARAM; otherwise a tight structural test: there is
    no party column, but a name column (an explicit ``Name`` or the product column)
    holds at least two band rows whose voucher *and* quantity columns are blank, with
    real product lines below. RAMAKRISHNA fails this test (its address text sits in the
    date column, so its band rows are not voucher-empty) and is left to ``tabular``.
    """
    header_idx = detect_header_row(rows, min_matches=3)
    if header_idx is None:
        return False
    if title_matches(rows):
        return True
    headers, col = _columns(rows, header_idx)
    if "party_name" in col:
        return False
    # A leading item/party "Code" column signals a multi-level (division/area/party)
    # code+name register (e.g. RAMAKRISHNA) whose marker rows masquerade as bands and
    # which this generic reader mis-aligns — leave those to ``tabular``.
    norm_headers = [normalize(h) for h in headers]
    if "code" in norm_headers:
        return False
    name_idx = next((i for i, h in enumerate(headers) if normalize(h) == "name"), None)
    band_col = name_idx if name_idx is not None else col.get("product_name")
    voucher_idx = [col[k] for k in ("invoice_number", "invoice_date") if k in col]
    if band_col is None or not voucher_idx:
        return False
    qty_idx = col.get("qty")
    bands = prods = 0
    for raw in rows[header_idx + 1: header_idx + 400]:
        if not raw:
            continue
        band_text = cell_text(raw[band_col]) if band_col < len(raw) else ""
        voucher_empty = all(not (cell_text(raw[i]) if i < len(raw) else "") for i in voucher_idx)
        qty_empty = qty_idx is None or not (cell_text(raw[qty_idx]) if qty_idx < len(raw) else "")
        joined = " ".join(cell_text(c) for c in raw)
        if band_text and voucher_empty and qty_empty and not is_subtotal(band_text) and not _TOTAL_RE.search(joined):
            bands += 1
        elif not voucher_empty:
            prods += 1
    return bands >= 2 and prods >= 2


def parse_partywise_band(rows):
    header_idx = detect_header_row(rows, min_matches=3)
    if header_idx is None:
        return [], {}
    headers, col = _columns(rows, header_idx)

    # A "Name" column that did not map to product_name is the customer column
    # (it maps to vendor_name by dict order); treat it as the party-band column.
    name_idx = None
    for idx, h in enumerate(headers):
        if normalize(h) == "name":
            name_idx = idx
            break
    prod_idx = col.get("product_name")
    if prod_idx is None and name_idx is not None:
        prod_idx = name_idx  # exports where the Name column holds the products too

    qty_idx = col.get("qty")
    amount_idx = col.get("amount")
    voucher_idx = [col[k] for k in ("invoice_number", "invoice_date") if k in col]
    # the column whose text marks a band: an explicit Name column, else the product
    # column (exports where the party band name shares the product column, e.g. a
    # "Product Name" column that also carries the customer header rows).
    band_idx = name_idx if name_idx is not None else prod_idx

    def at(raw, idx):
        return cell_text(raw[idx]) if (idx is not None and idx < len(raw)) else ""

    def transactional_empty(raw):
        idxs = [i for i in (voucher_idx + ([qty_idx] if qty_idx is not None else [])) if i is not None]
        if not idxs:
            return False
        return all(not at(raw, i) for i in idxs)

    records = []
    current_party = ""
    current_area = ""
    for raw in rows[header_idx + 1:]:
        if not raw:
            continue
        joined = " ".join(cell_text(c) for c in raw)
        first = cell_text(raw[0])
        if _MARKER_RE.match(first) or _TOTAL_RE.search(joined):
            continue

        band_text = at(raw, band_idx)
        product = at(raw, prod_idx)
        qty = at(raw, qty_idx)

        # band row: transactional columns empty, a name present, not a product line
        if band_text and transactional_empty(raw) and not is_numeric_qty(qty):
            current_area = _band_area(band_text) or current_area
            current_party = _clean_party(band_text)
            continue

        # AW_KANARA style: party in the Name column on the same row as its first product
        if name_idx is not None and prod_idx != name_idx:
            nm = at(raw, name_idx)
            if nm:
                current_area = _band_area(nm) or current_area
                current_party = _clean_party(nm)

        if not product or is_subtotal(product) or not current_party:
            continue
        # per-party / per-area subtotal rows repeat the party or area name in the
        # product column (e.g. JALARAM "LASALGAON" / "AHER MEDICAL ...") — drop them.
        if product.strip() in (current_party, current_area):
            continue
        record = {key: (raw[idx] if idx < len(raw) else "") for key, idx in col.items()}
        record["party_name"] = current_party
        if prod_idx is not None:
            record["product_name"] = at(raw, prod_idx)
        if current_area and not cell_text(record.get("party_location", "")):
            record["party_location"] = current_area
        if not cell_text(record.get("product_name", "")):
            continue
        records.append(record)

    detected = {raw: c for raw, c in
                {h: col_key for h, col_key in zip(headers, [None] * len(headers))}.items()}
    # report the real mapping
    detected = {}
    for idx, h in enumerate(headers):
        for key, cidx in col.items():
            if cidx == idx:
                detected[h] = key
    if band_idx is not None and band_idx < len(headers):
        detected[headers[band_idx]] = "party_name"
    return records, detected
