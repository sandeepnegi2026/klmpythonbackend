"""
Customer-as-band-header party-wise Excel reports.

A whole family of ERP exports puts the customer (party) name **not in a column**
but as a *band header row* that introduces a group of product/sale lines, e.g.

    Customer :AISHWARI MEDICAL              <- band (explicit prefix)
    HU01178  13-05-26  NIOSOL F CREAM ...   <- product lines for that customer
    Total: ...

or, with no prefix at all (the band is just a bare name row whose transactional
columns — invoice no / date — are blank, while the product rows below carry them):

    AAA REGENERATION CHEMIST&DRUG  AIROLI SEC-8  ...  22  5586.29   <- band
    IMXIA PLUS SHAMPOO  150ML  KLM L  23-05-26  9314  1 ...         <- product

The generic ``tabular`` parser maps the product columns correctly but never
attaches ``party_name`` (-> MISSING_REQUIRED_FIELD:party_name) because there is
no party column. This layout reuses the proven ``map_headers`` column mapping and
adds the one missing piece: carry the current band's customer name (and area) down
onto every product row until the next band. It is the Excel analogue of the
party-PDF band handling.

Two band styles are recognised:
  1. ``Customer :<name>`` (also ``Customer-<name>``) prefix rows  -> Pattern B
  2. bare-name rows whose invoice no/date columns are empty       -> Patterns C/D
"""
import re

from core.header_match import map_headers

from extractors.party_xlsx.constants import ADDR_BAND_RE, BARE_TOTAL_RE, CUSTOMER_BAND_RE
from extractors.party_xlsx.header_detect import detect_header_row
from extractors.party_xlsx.parse_common import cell_text, is_subtotal

# Section markers / block subtotals that head or close a company/area block (e.g.
# "Company Name : KLM ...", "Area Name : ABRAMA", "Company Total :") — skipped so they
# are not mistaken for product lines.
_SECTION_MARKER_RE = re.compile(r"^\s*(company|area|mfgr|manufacturer|division)(\s+(name|total))?\s*[:\-]", re.IGNORECASE)

# A bare "CODE-NAME,CITY,(phone)" band, e.g. "AKMN-A K MEDICAL & GENRAL STORE,NIMBAHERA,(900..)"
# or "0170-PRAKASH MEDICALS,BHILWARA". Used by Customer-Product-wise exports that carry NO
# voucher columns (just Product Code/Name/Pack/Qty/Value), so the bare-band-by-empty-voucher
# heuristic cannot fire — here the band is told apart from a product line by its blank
# qty/value columns plus the leading "code-" token.
#
# The code may carry a trailing dot ("1142.-KISHANGARH…") or an internal hyphen ("5-6-PRATISHTHA…"),
# which the older ``{2,12}`` alnum-only code missed — so those bands were emitted as blank-value
# junk rows AND (worse) their products were mis-attributed to the previous party. The code is now
# a lazy alnum/dot/hyphen run and the NAME is required to start with a letter, which fixes the
# split point (a "-<digit>" mid-code no longer ends the code). Product rows are never tested (the
# ``_qty_value_empty`` gate in ``_codename_band``), so this cannot reclassify a real product line.
_CODE_NAME_BAND_RE = re.compile(r"^\s*[A-Za-z0-9][A-Za-z0-9.\-]*?\s*-\s*([A-Za-z].*)$")

# A "Customer:" band that prefixes the firm with a bracketed customer code and appends a
# comma-separated address whose LAST field is the city, e.g.
#   "[A004] ARJUN MEDICAL, NEAR SKYLARK HOTEL, , AKOLA"  (micropro Customer-Wise export)
# Peel the "[code]" and address so party_name is the firm and party_location the city.
# GATED on the leading "[code]" token, so plain bands ("AISHWARI MEDICAL", "RATAN
# PHARMACY") never match and keep their existing party_name untouched.
_CODED_CUSTOMER_RE = re.compile(r"^\s*\[[A-Za-z0-9]+\]\s*(.+)$")
_PINCODE_TAIL_RE = re.compile(r"\s*-\s*\d{3,}\s*$")


def _split_coded_customer(text):
    """(party_name, location) for a "[code] NAME, addr, addr, CITY" band, else None."""
    match = _CODED_CUSTOMER_RE.match(text)
    if not match:
        return None
    parts = [p.strip() for p in match.group(1).split(",")]
    name = parts[0]
    if not name:
        return None
    loc = ""
    for seg in reversed(parts[1:]):
        if seg:
            loc = _PINCODE_TAIL_RE.sub("", seg).strip()  # drop a "-444001" pincode tail
            break
    return name, loc


def _qty_value_empty(raw, col):
    idxs = [col[k] for k in ("qty", "amount") if k in col]
    if not idxs:
        return False
    return all(not (cell_text(raw[i]) if i < len(raw) else "") for i in idxs)


def _codename_band(raw, col):
    """Return (party_name, location) for a 'CODE-NAME,CITY' band row, else None.

    Recognised only when the row's qty/value columns are blank — product lines always
    carry them, so this never reclassifies a real product row. The name may sit in
    column 0 or (when column 0 is an empty product-code cell) column 1.
    """
    if not _qty_value_empty(raw, col):
        return None
    probe = cell_text(raw[0]) or (cell_text(raw[1]) if len(raw) > 1 else "")
    if not probe or BARE_TOTAL_RE.match(probe):
        return None
    match = _CODE_NAME_BAND_RE.match(probe)
    if not match:
        return None
    body = match.group(1)
    name = body.split(",")[0].strip()
    if len(re.findall(r"[A-Za-z]", name)) < 3:
        return None
    rest = body.split(",")[1:]
    loc = re.sub(r"\(.*", "", rest[0]).strip() if rest else ""
    return name, loc


def _addr_from_row(raw):
    """Pull an ``Add :<address>`` value out of any cell of a band row."""
    for cell in raw:
        match = ADDR_BAND_RE.match(cell_text(cell))
        if match:
            return match.group(1).strip()
    return ""


def _band_location(raw, col):
    """Best-effort party location/area for a band row, preferring real signals.

    Order: a mapped party_location/party_area column, then an ``Add :<addr>`` cell,
    then — only as a last resort — column 1 when it is *not* a real mapped data field
    (covers the RUSHABH layout where the area sits in an unlabelled second column).
    Avoids the earlier bug of blindly taking ``raw[1]`` (which could be a GSTIN/code).
    """
    for key in ("party_location", "party_area"):
        idx = col.get(key)
        if idx is not None and idx < len(raw):
            value = cell_text(raw[idx])
            if value:
                return value
    addr = _addr_from_row(raw)
    if addr:
        return addr
    real_idx = {i for k, i in col.items() if not k.startswith("raw_")}
    if len(raw) > 1 and 1 not in real_idx:
        return cell_text(raw[1])
    return ""


def _is_merged_furniture(raw):
    """A merged banner/footer row repeats the SAME text across every populated cell — the vendor
    header block, or a trailing "Generated at 2026-06-27 12:13:05 by MAIN using MediVision
    Platinum" / "Powered by …" line the ERP writes into all columns. A real band or product row
    never carries 3+ identical populated cells (its name/qty/amount always differ), so this can
    only drop furniture, never data. Catches the merged variant the single-cell value-empty and
    bare-band gates miss (here the footer fills the voucher AND qty/amount columns)."""
    populated = [cell_text(c).strip() for c in raw if cell_text(c).strip()]
    return len(populated) >= 3 and len(set(populated)) == 1


def _is_merged_customer_band(raw):
    """A merged-across-columns row whose single repeated text is a "Customer:/Party:" band
    (smartpharma360 "Customer-Company wise Product Sales", micropro "Customer-Wise Product-Wise
    Sales"). The party is a merged cell spanning the whole table width, so unmerge replicates it
    into every column and _is_merged_furniture would drop it BEFORE the band branch runs, blanking
    the party for the whole group. Distinguish it from true furniture: identical populated cells,
    the text matches CUSTOMER_BAND_RE, and the captured name has >=3 letters (a real firm name,
    not a stray label). Furniture lines ("Generated at …", "Powered by …") never match, so they
    still drop."""
    populated = [cell_text(c).strip() for c in raw if cell_text(c).strip()]
    if len(populated) < 3 or len(set(populated)) != 1:
        return False
    band = CUSTOMER_BAND_RE.match(populated[0])
    return bool(band) and len(re.findall(r"[A-Za-z]", band.group(1))) >= 3


def _scheme_qty_idx(headers):
    """Index of a scheme/free QUANTITY column ("Scm qty", "Scheme Qty") — the free-goods count
    that MediVision / KLM ERPs print as its own column (core maps it to raw_scm_qty, so free_qty
    is otherwise lost). Excludes "Scm disc" (a monetary scheme discount, not a quantity). Returns
    None when there is no such column, so files without one keep their exact current behaviour."""
    for i, h in enumerate(headers):
        t = str(h).lower()
        if ("scm" in t or "scheme" in t) and ("qty" in t or "quantity" in t) and "disc" not in t:
            return i
    return None


def _is_bare_band(raw, voucher_idx):
    """A row with text in col0 but every invoice (voucher) column empty is a band.

    Requires at least one voucher column to exist; otherwise (e.g. a plain
    product+qty+value summary with no dates/bills) every row would look like a
    band, so bare-band detection is disabled when ``voucher_idx`` is empty.
    """
    if not voucher_idx:
        return False
    return all(not (cell_text(raw[i]) if i < len(raw) else "") for i in voucher_idx)


def parse_customer_product_banded(rows):
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

    voucher_idx = [col[k] for k in ("invoice_number", "invoice_date") if k in col]
    # Some ERP exports (micropro "Customer-Wise Product-Wise Sales Summary") carry the
    # customer in a *column* that is filled only on the FIRST product row of each group and
    # left blank on the continuation rows. When such a party_name column exists we carry the
    # last non-empty value (and its address) down onto the blank rows. Gated on the column
    # being present, so band-style files (which have no party_name column) are untouched.
    party_col = col.get("party_name")
    # Scheme/free quantity column ("Scm qty"): core maps it to raw_scm_qty, so free_qty is dropped.
    # When it exists and no real free_qty column was mapped, carry it into free_qty (so free
    # reconciles to the report's own per-party "Free" subtotal). Gated on the column existing —
    # files without a scheme column are untouched.
    scm_idx = _scheme_qty_idx(headers)
    free_from_scheme = scm_idx is not None and "free_qty" not in col

    records = []
    current_party = ""
    current_loc = ""
    col_party = ""
    col_loc = ""
    for raw in rows[header_idx + 1 :]:
        if not raw:
            continue
        if _is_merged_furniture(raw) and not _is_merged_customer_band(raw):
            continue
        first = cell_text(raw[0])

        if _SECTION_MARKER_RE.match(first):
            continue

        band = CUSTOMER_BAND_RE.match(first)
        if band:
            coded = _split_coded_customer(band.group(1))
            if coded:
                current_party, current_loc = coded
            else:
                current_party = band.group(1).strip()
                current_loc = _band_location(raw, col)
            continue

        if first and not BARE_TOTAL_RE.match(first) and _is_bare_band(raw, voucher_idx):
            current_party = first
            current_loc = _band_location(raw, col)
            continue

        # Voucher-less exports: the customer is a "CODE-NAME,CITY" band (qty/value blank).
        # Gated on there being no voucher columns so voucher-based files are untouched.
        if not voucher_idx:
            codename = _codename_band(raw, col)
            if codename:
                current_party, current_loc = codename
                continue

        record = {key: (raw[idx] if idx < len(raw) else "") for key, idx in col.items()}
        product = cell_text(record.get("product_name", ""))
        # Skip blanks, subtotals, and pure-separator markers. Some exports close the
        # report with an "*****" (or "-----") end-of-report row that is neither a band
        # nor a subtotal; without an alphanumeric it can never be a real product, so it
        # would otherwise be emitted as a spurious zero-value line under the last party.
        if not product or is_subtotal(product) or not re.search(r"[A-Za-z0-9]", product):
            continue
        # A real sale line always carries a value: when the qty/amount columns exist but are
        # ALL empty for this row, it is a report footer/branding line (e.g. "Powered By
        # SwilERP for Retail…" printed after the grand total in its own single cell) that
        # merely looks like a product. Gated on those columns being present, so files without
        # a qty/amount column are unaffected. EXCEPTION: a scheme-only FREE-goods line (free
        # goods have no sale value but a positive scheme qty) is printed on its own row — keep
        # those so free_qty reconciles to the band's Free subtotal (footers carry no scheme qty).
        scheme_qty = cell_text(raw[scm_idx]) if scm_idx is not None and scm_idx < len(raw) else ""
        has_scheme = scheme_qty.strip() not in ("", "0", "0.0", "-")
        value_cols = [k for k in ("qty", "amount") if k in col]
        if value_cols and all(not cell_text(record.get(k, "")) for k in value_cols) and not has_scheme:
            continue
        if free_from_scheme:
            record["free_qty"] = raw[scm_idx] if (scm_idx is not None and scm_idx < len(raw)) else ""
        # Columnar carry-down: remember the last non-empty party (and address) from the
        # party_name column and fill it onto the blank continuation rows below it.
        if party_col is not None:
            col_name = cell_text(record.get("party_name", ""))
            if col_name:
                col_party = col_name
                col_loc = cell_text(record.get("party_location", ""))
            elif col_party:
                record["party_name"] = col_party
                if col_loc and not cell_text(record.get("party_location", "")):
                    record["party_location"] = col_loc
        if current_party:
            record["party_name"] = current_party
        if current_loc and not cell_text(record.get("party_location", "")):
            record["party_location"] = current_loc
        records.append(record)

    return records, detected
