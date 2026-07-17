import re

# KLM "COMPANY, CUSTOMER AND INVOICE SALES" (SRI VASAVI MEDICAL DISTRIBUTORS).
#
# Monospaced DOSPrinter export. Structure (repeats per page):
#   SRI VASAVI MEDICAL DISTRIBUTORS
#   From : 01/05/2026 COMPANY, CUSTOMER AND INVOICE SALES
#   To : 31/05/2026
#   Company : KLM(COSMO DIVISION) Page : 1
#   ----
#   Invoice Invoice Product Name Packing Batch Quantity Free Price Value Discount
#   Number Date
#   ----
#   Customer : <NAME>,<TOWN>          <- party band (town after FIRST comma)
#   ----------
#   <INV> <DD/MM/YYYY> <product ...> <packing> <batch> <Qty> <Free> <Price> <Value> <Discount>
#   ...
#   Customer Totals : <value> <disc>  <- per-band footer
#   ----
#   Company Total : KLM(...) <value> <disc>
#   Grand Total : <value> <disc>
#
# Invoice rows are single lines. The 5 trailing numeric columns (Qty Free Price
# Value Discount) are ALWAYS printed with a decimal point ('5.0', '0.00'), so the
# NUM pattern requires a '.' — that keeps the digit-only tail of a two-token batch
# ('DP 436') from being swallowed as Qty.
#
# The Customer band is NOT re-printed after a page header: continuation rows (and
# sometimes only the 'Customer Totals :' footer) appear under the repeated
# title/column-header block, so the active party MUST carry across page breaks.
# We therefore never reset the party on page-header noise.
#
# Text-based (word x-position not needed: one invoice per line, no interior blank
# columns). Rows are emitted only while a "Customer :" band is active, so
# title/header/footer noise cannot leak in.

# 5 trailing numeric columns; decimal point required (see note above).
_NUM = r'-?\d[\d,]*\.\d+'

# party band: Customer : <name>,<town>
_BAND_RE = re.compile(r'^Customer\s*:\s*(?P<body>.+)$', re.I)

# invoice row: <INV> <date> <head> <qty> <free> <rate> <value> <disc>
_ROW_RE = re.compile(
    r'^(?P<inv>[A-Z]{2}\d{4,})\s+'
    r'(?P<date>\d{2}/\d{2}/\d{4})\s+'
    r'(?P<head>.+?)\s+'
    r'(?P<qty>' + _NUM + r')\s+'
    r'(?P<free>' + _NUM + r')\s+'
    r'(?P<rate>' + _NUM + r')\s+'
    r'(?P<value>' + _NUM + r')\s+'
    r'(?P<disc>' + _NUM + r')\s*$'
)

# lines that are never invoice rows / never party bands
_SKIP_RE = re.compile(
    r'^\s*('
    r'-{3,}'                      # dashed separators
    r'|Customer\s+Totals\s*:'     # per-band footer
    r'|Company\s+Total\s*:'       # per-company footer
    r'|Grand\s+Total\s*:'         # document footer
    r'|Company\s*:'               # Company : KLM(...) Page : N
    r'|From\s*:'                  # From : <date> ...
    r'|To\s*:'                    # To : <date>
    r'|Page\s*:'                  # (defensive) page markers
    r'|Invoice\s+Invoice\s'       # column header line 1
    r'|Number\s+Date'             # column header line 2
    r'|DOSPrinter\s'              # footer noise
    r')', re.I)

# packing unit token, e.g. '60GM', 'GM', 'ML', "10'S", '2ML' (case-insensitive)
_PACK_RE = re.compile(r"^\d*('?S|GM|MG|KG|ML|G|L)$", re.I)

# bare-number token that precedes a unit token, e.g. '75' in '75 GM'
_BARE_NUM_RE = re.compile(r'^\d+$')

# batch lead-token (the FIRST of a two-token batch) — must NOT be a pack unit.
#  'DP' in 'DP 436', 'K-24' in 'K-24 NS'
_BATCH_LEAD_RE = re.compile(r"^[A-Z]{1,4}(-?\d+)?$")
# batch tail candidates that mark a two-token batch: bare digits ('436') or a
# short all-uppercase suffix ('NS').
_BATCH_TAIL_DIGITS_RE = re.compile(r'^\d{2,6}$')
_BATCH_TAIL_ALPHA_RE = re.compile(r'^[A-Z]{1,3}$')


def _split_band(body):
    """Split a 'Customer : <name>,<town>' body into (party, town).

    Town is everything after the FIRST comma; leading commas are stripped
    ('SRI HARI MEDICALS,,CHITTOOR'); a glued trailing 10-digit phone is dropped
    ('...NARES 9032187773'); a trailing dot is removed from both sides.
    """
    if "," in body:
        party, town = body.split(",", 1)
    else:
        party, town = body, ""
    town = town.lstrip(", ").strip()
    # drop a trailing 10-digit phone number ('SRIKALAHASTI NARES 9032187773')
    town = re.sub(r'\s*\b\d{10}\b\s*$', '', town).strip()
    party = party.strip().rstrip('.').strip()
    town = town.rstrip('.').strip()
    return party, town


def _split_head(head):
    """Right-to-left split of the product/packing/batch head.

    Returns (product_name, packing, batch). Order: pop batch (1 or 2 tokens),
    then pop packing (unit token optionally preceded by a bare number); the
    remainder is the product name (kept as printed, vendor right-truncates it).
    """
    toks = head.split()
    if not toks:
        return "", "", ""

    # (a) batch — pop last token; if this is a two-token batch ('DP 436' /
    # 'K-24 NS'), also pop the lead token.
    batch_parts = [toks.pop()]
    if toks:
        tail = batch_parts[0]
        lead = toks[-1]
        two_token = False
        if not _PACK_RE.match(lead):
            if _BATCH_TAIL_DIGITS_RE.match(tail) and _BATCH_LEAD_RE.match(lead):
                # 'DP 436' — lead like 'DP'/'K-24', tail bare digits
                two_token = True
            elif _BATCH_TAIL_ALPHA_RE.match(tail) and _BATCH_LEAD_RE.match(lead):
                # 'K-24 NS' — lead like 'K-24', tail short uppercase
                two_token = True
        if two_token:
            batch_parts.insert(0, toks.pop())
    batch = " ".join(batch_parts)

    # (b) packing — trailing unit token, optionally preceded by a bare number.
    packing = ""
    if toks and _PACK_RE.match(toks[-1]):
        pk = [toks.pop()]
        if toks and _BARE_NUM_RE.match(toks[-1]):
            pk.insert(0, toks.pop())
        packing = " ".join(pk)

    # (c) remainder = product name
    product = " ".join(toks).strip()
    return product, packing, batch


def parse_klm_company_customer_invoice(text):
    headers = ["Party Name", "Area", "Invoice No", "Invoice Date",
               "Product Name", "Packing", "Batch",
               "Qty", "Free", "Rate", "Amount", "Discount"]
    rows = []

    party = ""
    town = ""
    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            continue

        m = _BAND_RE.match(s)
        if m:
            party, town = _split_band(m.group("body"))
            continue

        if _SKIP_RE.match(s):
            # noise/footers/page-headers — do NOT reset the active party (bands
            # carry across page breaks).
            continue

        if not party:
            continue

        rm = _ROW_RE.match(s)
        if not rm:
            continue

        product, packing, batch = _split_head(rm.group("head").strip())
        if not product:
            continue

        rows.append([
            party,
            town,
            rm.group("inv"),
            rm.group("date"),
            product,
            packing,
            batch,
            rm.group("qty"),
            rm.group("free"),
            rm.group("rate"),
            rm.group("value"),
            rm.group("disc"),
        ])

    return headers, rows
