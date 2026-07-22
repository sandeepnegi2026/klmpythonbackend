import re

# SREE SWATHI MEDICALS "COMPANY AND PRODUCT, AREA, INVOICE".
#
# Monospaced DOSPrinter export, PRODUCT-major (sibling of the customer-major
# klm_company_customer_invoice). Structure (repeats per company/page):
#   SREE SWATHI MEDICALS
#   From : 01/05/2026 COMPANY AND PRODUCT, AREA, INVOICE
#   To : 31/05/2026
#   Company Name : KLM COSMO DIVISION Page : 1
#   ----
#   Invoice Invoice Customer Name Quantity Free Value Discount
#   Number  Date    Locality                        Amount
#   ----
#   Product Name : 3703 EKRAN SOFT SILICONE SUNSCREEN GEL 50GM   <- product band
#   Area Name : TIRUPATHI                                        <- area section
#   <INV> <DD/MM/YYYY> <Customer Name> <Qty> <Free> <Value> <Discount>
#   <Locality>                                          <- wrapped 2nd line of Customer col
#   ...
#   Area Total : <area> <qty> <free> <value> <disc>     <- per-area footer
#   Product Total : <product> <qty> <free> <value> <disc>
#   Company Total : <company> <value> <disc>
#   Grand Total : <value> <disc>
#
# The 4 trailing numeric columns (Qty Free Value Discount) are ALWAYS printed
# with a decimal point ('5.0', '0.00', '2,576.25'), so the NUM pattern requires a
# '.' and the Customer Name is OPTIONAL: some invoices print no customer name
# ('AS00691 18/05/2026 5.0 0.0 2694.90 0.00'), so the name segment must be able to
# be empty (no mandatory separating space) or those rows — and their Value — drop.
#
# The active Product and Area bands are NOT re-printed after a repeated page
# header, so both MUST carry across page breaks (never reset on header noise).
# sum(Value over all invoice rows) reconciles EXACTLY to the printed Grand Total.

# 4 trailing numeric columns; decimal point required.
_NUM = r"-?\d[\d,]*\.\d+"

# invoice row: <INV> <date> [<customer name>] <qty> <free> <value> <disc>
# INV is 1-5 letters then >=3 digits ('AS00589'); the customer-name segment is
# optional (non-greedy, may be empty), and the four decimal columns anchor the tail.
_ROW_RE = re.compile(
    r"^(?P<inv>[A-Za-z]{1,5}\d{3,})\s+"
    r"(?P<date>\d{2}/\d{2}/\d{4})\s+"
    r"(?P<name>.*?)\s*"
    r"(?P<qty>" + _NUM + r")\s+"
    r"(?P<free>" + _NUM + r")\s+"
    r"(?P<value>" + _NUM + r")\s+"
    r"(?P<disc>" + _NUM + r")\s*$"
)

# product band: "Product Name : <code> <name>" (drop a leading numeric product code)
_PROD_RE = re.compile(r"^Product\s+Name\s*:\s*(?P<body>.+)$", re.I)
# area band: "Area Name : <area>"
_AREA_RE = re.compile(r"^Area\s+Name\s*:\s*(?P<area>.*)$", re.I)

# structural lines that are never invoice rows / bands (and must NOT be treated as
# a wrapped locality line either).
_SKIP_RE = re.compile(
    r"^\s*("
    r"-{3,}"                       # dashed separators
    r"|Area\s+Total\s*:"          # per-area footer
    r"|Product\s+Total\s*:"       # per-product footer
    r"|Company\s+Total\s*:"       # per-company footer
    r"|Grand\s+Total\s*:"         # document footer
    r"|Company\s+Name\s*:"        # Company Name : KLM ... Page : N
    r"|From\s*:"                  # From : <date> ...
    r"|To\s*:"                    # To : <date>
    r"|Page\s*:"                  # (defensive) page markers
    r"|Invoice\s+Invoice\b"       # column header line 1
    r"|Number\s+Date\b"           # column header line 2
    r")", re.I)


def parse_sree_swathi_company_product_area_invoice(text):
    headers = ["Party Name", "Area", "Product Name", "Invoice No",
               "Invoice Date", "Qty", "Free", "Amount", "Discount"]
    rows = []

    product = ""
    area_section = ""
    pending = None   # index of the last emitted row still awaiting its Locality line

    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            continue

        pm = _PROD_RE.match(s)
        if pm:
            body = pm.group("body").strip()
            # drop a leading numeric product code ("3703 EKRAN ..." -> "EKRAN ...")
            body = re.sub(r"^\d+\s+", "", body)
            product = body.strip()
            pending = None
            continue

        am = _AREA_RE.match(s)
        if am:
            area_section = am.group("area").strip()
            pending = None
            continue

        if _SKIP_RE.match(s):
            pending = None
            continue

        rm = _ROW_RE.match(s)
        if rm:
            name = rm.group("name").strip()
            rows.append([
                name,
                area_section,                 # party_location; overwritten by wrapped Locality
                product,
                rm.group("inv"),
                rm.group("date"),
                rm.group("qty"),
                rm.group("free"),
                rm.group("value"),
                rm.group("disc"),
            ])
            pending = len(rows) - 1
            continue

        # A bare line right after an invoice row is that customer's wrapped Locality
        # (2nd line of the Customer column). Attach it as the row's Area/location.
        if pending is not None and product:
            rows[pending][1] = s.strip()
            pending = None

    return headers, rows
