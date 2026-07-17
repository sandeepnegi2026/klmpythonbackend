import re

# SmartPharma360 "Customer-Company wise Product Sales"
# (SRI BABA MEDICAL DISTRIBUTORS).
#
# Text export (footer 'Powered by SmartPharma360'). Structure (spans pages, the
# report is NOT replicated per page — it flows continuously):
#
#   SRI BABA MEDICAL DISTRIBUTORS
#   <address lines>
#   Customer-Company wise Product Sales
#   ( 01-06-2026 to 30-06-2026 )
#   Page: 1/10
#   Inv. No. Inv Date Product Name Batch Qty Free Rate Value
#   Company Name: KLM COSMO C1                 <- division band (8 KLM divisions)
#   Customer: APOLLO PHARMACIES LTD 3 (...)-GUDIVADA-3-GUDIVADA-3   <- party band
#   KLM COSMO C1 SI26-031724 08-06-2026 EKRAN-30 SILICON SUN… CL504 1 0 308.47 308.47
#   Invalid date 1 0 308.47 308.47            <- per-customer subtotal (ERP bug label)
#   ...
#   Invalid date 8 0 2989.54 2989.54          <- per-company subtotal
#   Invalid date 192 0 34744.81 41997.62      <- grand total (last one)
#   Powered by SmartPharma360(cid:0) Taken by: ...
#
# Data row layout:
#   <COMPANY PREFIX> <INV> <DD-MM-YYYY> <product ...> <batch> <qty> <free> <rate> <value>
# - COMPANY PREFIX equals the current 'Company Name:' band (e.g. 'KLM COSMO C1',
#   'KLM-OPTHAL'); it is stripped off (division comes from the band).
# - INV token is r'SI\d{2}-\d{5,}'.
# - The 4 trailing tokens are qty free rate value; the token immediately before
#   them is the batch. Product name may be ellipsis-truncated ('SILICON SUN…').
#
# Column map: Qty->qty, Free->free_qty, Rate->rate, Value->amount.
# Reconcile: sum(qty)=192, sum(free)=0, sum(amount)=41,997.62 (printed grand total).
#
# All 'Invalid date ...' lines are subtotals (per-customer / per-company / grand)
# and are skipped. Party bands are 'NAME-AREA-TOWN' joined by dashes; the last
# dash segment is the town (party_location), the rest is the party name.

_INV_RE = re.compile(r'SI\d{2}-\d{5,}')
_DATE_RE = re.compile(r'\d{2}-\d{2}-\d{4}')
_NUM = r'-?\d[\d,]*(?:\.\d+)?'

# full data row: <company prefix> <inv> <date> <head=product+batch> qty free rate value
_ROW_RE = re.compile(
    r'^(?P<prefix>.+?)\s+'
    r'(?P<inv>SI\d{2}-\d{5,})\s+'
    r'(?P<date>\d{2}-\d{2}-\d{4})\s+'
    r'(?P<head>.+?)\s+'
    r'(?P<qty>' + _NUM + r')\s+'
    r'(?P<free>' + _NUM + r')\s+'
    r'(?P<rate>' + _NUM + r')\s+'
    r'(?P<value>' + _NUM + r')\s*$'
)

_COMPANY_RE = re.compile(r'^Company\s*Name\s*:\s*(?P<name>.+)$', re.I)
_CUSTOMER_RE = re.compile(r'^Customer\s*:\s*(?P<body>.+)$', re.I)

# noise / subtotal lines that are never data rows or bands
_SKIP_RE = re.compile(
    r'^\s*('
    r'Invalid\s+date'                       # subtotal rows (ERP bug label)
    r'|Page\s*:'                            # Page: 1/10
    r'|Powered\s+by\s+SmartPharma'          # footer
    r'|Inv\.\s*No\.'                        # column header
    r'|Customer-Company\s+wise'             # title
    r'|\(\s*\d{2}-\d{2}-\d{4}\s+to'         # date range line
    r')', re.I
)


def _split_customer(body):
    """Split 'NAME-AREA-TOWN' into (party_name, party_location).

    The customer heading joins name, area and town with '-'. Names themselves may
    contain '-', '(', ',', so we peel only the trailing town (last dash segment)
    as the location and keep the remainder (minus the area segment) as the name.
    Tolerates empty segments ('BALAJI MEDICAL STORES(--GUDLAVALLERU').
    """
    body = body.strip()
    parts = body.split("-")
    if len(parts) >= 3:
        town = parts[-1].strip()
        # name = everything except the last two segments (area, town)
        name = "-".join(parts[:-2]).strip()
        # if stripping the area left the name empty, keep everything before town
        if not name:
            name = "-".join(parts[:-1]).strip()
    elif len(parts) == 2:
        name = parts[0].strip()
        town = parts[1].strip()
    else:
        name = body
        town = ""
    return name.rstrip(",( ").strip(), town.rstrip(".").strip()


def _split_head(head, prefix):
    """Return (product_name, batch) from the product+batch head.

    The batch is the LAST whitespace token; the remainder is the product name.
    Also defensively strips a leading company prefix if it slipped into the head.
    """
    head = head.strip()
    if prefix and head.startswith(prefix):
        head = head[len(prefix):].strip()
    toks = head.split()
    if not toks:
        return "", ""
    batch = toks.pop()
    product = " ".join(toks).strip()
    return product, batch


def parse_smartpharma_customer_company_sales(text):
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

        product, batch = _split_head(rm.group("head"), rm.group("prefix").strip())
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
