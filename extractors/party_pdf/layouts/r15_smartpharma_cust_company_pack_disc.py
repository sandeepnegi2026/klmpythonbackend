import re

# SmartPharma360 "Customer-Company wise Product Sales" -- Packing/Mrp/Discount variant
# (PRUDHVI PHARMACEUTICALS).
#
# GATE TOKEN (spaces-stripped, lowercased column-header run, unique):
#   "inv.no.invdateproductnamepackingbatchmrpqtyfreeratediscountvalue"
#   (pair it with the title "customer-companywiseproductsales")
#
# This is a third sibling of smartpharma_customer_company_sales (SRI BABA) and
# r15_smartpharma_cust_company_url (ABHIRAM). Both existing parsers read 0 rows on
# this file because the row/column shape differs:
#   1. Extra PACKING, MRP and DISCOUNT columns:
#        header = Inv. No. | Inv Date | Product Name | Packing | Batch | Mrp |
#                 Qty | Free | Rate | Discount | Value
#      whereas the siblings are ...Product Name | Batch | Qty | Free | Rate | Value.
#   2. INV token is 'SIP26-005669' style (r'SIP\d{2}-\d{5,}'), NOT the sibling
#      'SI26-031724' (r'SI\d{2}-\d{5,}') or 'SI-AB-26-006298' styles.
#   3. Data rows have NO leading 'Company Name:' prefix (division comes from the
#      band), and there is no trailing Invoice-URL column.
#
# Structure (flows continuously across pages, header/footer repeat per page):
#   PRUDHVI PHARMACEUTICALS
#   <address lines>
#   Customer-Company wise Product Sales
#   ( 28-04-2026 to 31-05-2026 )
#   Page: 1/11
#   Inv. No. Inv Date Product Name Packing Batch Mrp Qty Free Rate Discount Value
#   Company Name: KLM - COSMO                              <- division band
#   Customer: OPTIVAL HEALTH SOLUTIONS PVT LTD-2974298-VIJAYAWADA 7  <- party band
#   SIP26-005669 28-04-2026 IMXIA F LOTION 60ml IKT-2506 759.38 3 0 520.72 -3 1562.16
#   Invalid date 9 0 1798.38 3807.27          <- per-customer subtotal (ERP bug label)
#   ...
#   Invalid date 377 0 30315.41 75860.10      <- grand total (last one)
#   Powered by SmartPharma360(cid:0) Taken by: ...
#
# Data row layout:
#   <INV> <DD-MM-YYYY> <product ...> <packing> <batch> <mrp> <qty> <free> <rate>
#   <discount> <value>
# - The LAST 6 whitespace tokens are mrp qty free rate discount value (all numeric).
#   The token before them is the batch; the token before the batch is the packing
#   ('60ml' / '30gm' / '150ml' or a bare number like '10' / '20'); the rest is the
#   product name.
#
# Column map (sales report -- SACRED: qty and value are separate columns):
#   Qty->qty, Free->free_qty, Rate->rate, Value->amount. Mrp/Packing/Discount are
#   NOT emitted (Discount here is a small integer scheme %, not a returns column;
#   MRP is a reference price). qty*rate == value on every row (verified).
# Reconcile: sum(qty)=377, sum(amount)=75,860.10 (printed grand total).
#
# All 'Invalid date ...' lines are subtotals (per-customer / per-company / grand)
# and are skipped. Party bands are 'NAME-AREA-TOWN' joined by dashes; the last dash
# segment is the town (party_location), the remainder minus the area segment is the
# name. A trailing bare number after the town ('...VIJAYAWADA 7') is left in the
# town field verbatim (matches the sibling behaviour).

_NUM = r'-?\d[\d,]*(?:\.\d+)?'
_INV = r'SIP\d{2}-\d{4,}'

# full data row: <inv> <date> <head=product+packing+batch> mrp qty free rate disc value
_ROW_RE = re.compile(
    r'^(?P<inv>' + _INV + r')\s+'
    r'(?P<date>\d{2}-\d{2}-\d{4})\s+'
    r'(?P<head>.+?)\s+'
    r'(?P<mrp>' + _NUM + r')\s+'
    r'(?P<qty>' + _NUM + r')\s+'
    r'(?P<free>' + _NUM + r')\s+'
    r'(?P<rate>' + _NUM + r')\s+'
    r'(?P<disc>' + _NUM + r')\s+'
    r'(?P<value>' + _NUM + r')\s*$'
)

_COMPANY_RE = re.compile(r'^Company\s*Name\s*:\s*(?P<name>.+)$', re.I)
_CUSTOMER_RE = re.compile(r'^Customer\s*:\s*(?P<body>.+)$', re.I)

# noise / subtotal lines that are never data rows or bands
_SKIP_RE = re.compile(
    r'^\s*('
    r'Invalid\s+date'                       # subtotal rows (ERP bug label)
    r'|Page\s*:'                            # Page: 1/11
    r'|Powered\s+by\s+SmartPharma'          # footer
    r'|Inv\.\s*No\.'                        # column header
    r'|Customer-Company\s+wise'             # title
    r'|\(\s*\d{2}-\d{2}-\d{4}\s+to'         # date range line
    r')', re.I
)


def _split_customer(body):
    """Split 'NAME-AREA-TOWN' into (party_name, party_location)."""
    body = body.strip()
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
    """Return (product_name, batch) from the product+packing+batch head.

    Layout is '<product ...> <packing> <batch>'. The batch is the LAST token; the
    packing is the second-to-last token. Both packing and batch are dropped from the
    product name (batch is emitted; packing is not a column we retain).
    """
    head = head.strip()
    toks = head.split()
    if not toks:
        return "", ""
    batch = toks.pop()           # trailing batch token
    if toks:
        toks.pop()               # drop packing token (not retained)
    product = " ".join(toks).strip()
    return product, batch


def parse_smartpharma_cust_company_pack_disc(text):
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
