import re

# SmartPharma360 "Customer-Company wise Product Sales (Reps)" -- URL variant
# (ABHIRAM MEDICAL AGENCIES).
#
# GATE TOKEN (spaces-stripped, lowercased column header, tail-anchored, unique):
#   "inv.no.invdateproductnamebatchqtyfreeratevalueinvoiceurl"
#
# This is a sibling of smartpharma_customer_company_sales (SRI BABA) but differs
# structurally so the SRI-BABA parser reads 0 rows on it:
#   1. Data rows have NO leading 'Company Name:' prefix -- the division comes only
#      from the 'Company Name:' band; each row starts directly with the INV token.
#   2. INV token is 'SI-AB-26-006298' style (r'SI-[A-Z]{2}-\d{2}-\d+'),
#      NOT the 'SI26-031724' (r'SI\d{2}-\d{5,}') style of the sibling.
#   3. There is a trailing 'Invoice URL' column ('https://url.smartpharma360.in/..'
#      or an ellipsis-truncated 'https://url.smartphar…') AFTER the value.
#
# Structure (flows continuously across pages, NOT replicated per page):
#   ABHIRAM MEDICAL AGENCIES
#   <address lines>
#   Customer-Company wise Product Sales (Reps)
#   ( 01-05-2026 to 31-05-2026 )
#   Page: 1/7
#   Inv. No. Inv Date Product Name Batch Qty Free Rate Value Invoice URL
#   Company Name: KLM LABORATORIES ( PEDI AND GYNIC )        <- division band
#   Customer: ACHYUT MEDICAL AND GENERAL STORES-AZAMPURA, MEDAK-MEDAK   <- party band
#   SI-AB-26-006298 22-05-2026 SOFIDEW BABY MASSGE…AK3601 20 5 176.27 3525.40 https://...
#   Invalid date 40 11 315.25 6305.00       <- per-customer subtotal (ERP bug label)
#   ...
#   Invalid date 109 56 2981.07 21684.83    <- per-company subtotal
#   Invalid date 961 380 26246.84 167964.02 <- grand total (last one)
#   Powered by SmartPharma360(cid:0) Taken by: ...
#
# Data row layout:
#   <INV> <DD-MM-YYYY> <product ...> <batch> <qty> <free> <rate> <value> <url?>
# - The 4 numeric tokens immediately before the trailing URL (or EOL) are
#   qty free rate value; the token before them is the batch; the rest is product.
# - Product may be ellipsis-truncated ('SOFIDEW BABY MASSGE…AK3601' -- '…' glues
#   the truncated name to the batch with no space).
#
# Column map (sales report): Qty->qty, Free->free_qty, Rate->rate, Value->amount.
# All 'Invalid date ...' lines are subtotals (customer / company / grand) -> skipped.
# Party bands are 'NAME-AREA-TOWN' joined by dashes; last dash segment is the town
# (party_location), remainder minus the area segment is the name. A trailing phone
# number ('...KAMAREDDY 9030301631') is stripped.

_NUM = r'-?\d[\d,]*(?:\.\d+)?'
_INV = r'SI-[A-Z]{2}-\d{2}-\d+'

# full data row: <inv> <date> <head=product+batch> qty free rate value <url?>
_ROW_RE = re.compile(
    r'^(?P<inv>' + _INV + r')\s+'
    r'(?P<date>\d{2}-\d{2}-\d{4})\s+'
    r'(?P<head>.+?)\s+'
    r'(?P<qty>' + _NUM + r')\s+'
    r'(?P<free>' + _NUM + r')\s+'
    r'(?P<rate>' + _NUM + r')\s+'
    r'(?P<value>' + _NUM + r')'
    r'(?:\s+https?://\S+)?\s*$'
)

_COMPANY_RE = re.compile(r'^Company\s*Name\s*:\s*(?P<name>.+)$', re.I)
_CUSTOMER_RE = re.compile(r'^Customer\s*:\s*(?P<body>.+)$', re.I)

# noise / subtotal lines that are never data rows or bands
_SKIP_RE = re.compile(
    r'^\s*('
    r'Invalid\s+date'                       # subtotal rows (ERP bug label)
    r'|Page\s*:'                            # Page: 1/7
    r'|Powered\s+by\s+SmartPharma'          # footer
    r'|Inv\.\s*No\.'                        # column header
    r'|Customer-Company\s+wise'             # title
    r'|\(\s*\d{2}-\d{2}-\d{4}\s+to'         # date range line
    r')', re.I
)

_TRAIL_PHONE_RE = re.compile(r'\s+\d{10}\s*$')


def _split_customer(body):
    """Split 'NAME-AREA-TOWN' into (party_name, party_location).

    The customer heading joins name, area and town with '-'. Names themselves may
    contain '-', '(', ',', '{', so we peel only the trailing town (last dash
    segment) as the location and keep the remainder (minus the area segment) as
    the name. A trailing 10-digit phone is stripped first.
    """
    body = _TRAIL_PHONE_RE.sub("", body).strip()
    parts = body.split("-")
    if len(parts) >= 3:
        town = parts[-1].strip()
        name = "-".join(parts[:-2]).strip()
        if not name:
            name = "-".join(parts[:-1]).strip()
    elif len(parts) == 2:
        name = parts[0].strip()
        town = parts[1].strip()
    else:
        name = body
        town = ""
    return name.rstrip(",( ").strip(), town.rstrip(".").strip()


def _split_head(head):
    """Return (product_name, batch) from the product+batch head.

    The batch is the LAST whitespace token; the remainder is the product name.
    Ellipsis-truncated names glue to the batch with '…' and no space
    ('SOFIDEW BABY MASSGE…AK3601'): split on the '…' so the batch stays clean.
    """
    head = head.strip()
    toks = head.split()
    if not toks:
        return "", ""
    batch = toks.pop()
    if "…" in batch:            # ellipsis glued name…batch -> keep batch tail
        pname, _, btail = batch.rpartition("…")
        toks.append(pname + "…")
        batch = btail
    product = " ".join(toks).strip()
    return product, batch


def parse_smartpharma_cust_company_url(text):
    headers = ["Party Name", "Area", "Division", "Invoice No", "Invoice Date",
               "Product Name", "Batch", "Qty", "Free", "Rate", "Amount"]
    rows = []

    party = ""
    town = ""
    company = ""
    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            continue

        cm = _COMPANY_RE.match(s)
        if cm:
            company = cm.group("name").strip()
            continue

        pm = _CUSTOMER_RE.match(s)
        if pm:
            party, town = _split_customer(pm.group("body"))
            continue

        if _SKIP_RE.match(s):
            continue

        rm = _ROW_RE.match(s)
        if not rm:
            continue
        if not party:
            continue

        product, batch = _split_head(rm.group("head"))
        if not product:
            continue

        rows.append([
            party,
            town,
            company,
            rm.group("inv"),
            rm.group("date"),
            product,
            batch,
            rm.group("qty").replace(",", ""),
            rm.group("free").replace(",", ""),
            rm.group("rate").replace(",", ""),
            rm.group("value").replace(",", ""),
        ])

    return headers, rows
