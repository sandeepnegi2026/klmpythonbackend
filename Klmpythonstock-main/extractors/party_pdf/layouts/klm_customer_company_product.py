import re

# KLM "Customer,Company And Product Sales" (SRI DURGA SRINIVASA PHARMA & VETS).
#
# Dashed-band party report. Structure:
#   SRI DURGA SRINIVASA PHARMA & VETS
#   Customer,Company And Product Sales
#   From 01/05/2026 To 27/05/2026        Page : 1
#   Company :KLM (<DIVISION>)
#   ----
#   Product Name Packing Qty Free Rate Amount      <- fixed column header (repeats/page)
#   ----
#   Customer :<NAME>  Add :<CITY>                  <- party band (area follows "Add :")
#   ----
#   <PRODUCT NAME ...> <PACKING> <Qty> <Free> <Rate> <Amount>   <- single-line rows
#   ...
#   Total: <amount>                                <- per-band footer
#   ----
#
# Rows are clean single lines (no wrap / no batch / no inv / no date). Each row's
# last 4 whitespace tokens are qty free rate amount (floats like "4.0 0.0 242.86
# 971.44"); the token immediately before them is the packing (30gm/10s/100ml/...),
# and everything before that is the product name.
#
# The parser is intentionally text-based (word x-position not needed: the vendor
# prints one product per line with no interior blank columns). Only emits rows
# while a "Customer :" band is active, so title/header/footer noise cannot leak in.


def parse_klm_customer_company_product(text, file_bytes=None):
    headers = ["Party Name", "Area", "Product Name", "Packing",
               "Qty", "Free", "Rate", "Amount"]
    rows = []

    # party band:  Customer :<name>  Add :<area>
    # area follows "Add :" (NOT a comma). The vendor may right-truncate the
    # customer name (e.g. "...STORES(PT") — keep it as printed.
    band_re = re.compile(r'^Customer\s*:\s*(?P<party>.+?)\s+Add\s*:\s*(?P<area>.*)$', re.I)

    # product row: <head> <qty> <free> <rate> <amount>  (trailing 4 numerics)
    NUM = r'-?\d[\d,]*\.?\d*'
    row_re = re.compile(
        r'^(?P<head>.+?)\s+(?P<qty>' + NUM + r')'
        r'\s+(?P<free>' + NUM + r')'
        r'\s+(?P<rate>' + NUM + r')'
        r'\s+(?P<amt>' + NUM + r')\s*$'
    )

    # lines that are never product rows / never party bands
    skip_re = re.compile(
        r'^\s*('
        r'-{3,}'                              # dashed separators
        r'|Total\s*:'                         # per-band footer
        r'|Grand\s*Total'                     # (defensive) grand total
        r'|Page\s*:'                          # page markers
        r'|From\s+\d'                         # From <date> ... line
        r'|Company\s*:'                       # Company :KLM (...)
        r'|Customer\s*,\s*Company'            # title line
        r'|Product\s+Name\s+Packing'          # column header
        r')', re.I)

    party = ""
    area = ""
    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            continue

        m = band_re.match(s)
        if m:
            party = m.group('party').strip()
            area = m.group('area').strip()
            continue

        if skip_re.match(s):
            continue

        if not party:
            continue

        rm = row_re.match(s)
        if not rm:
            continue

        head = rm.group('head').strip()
        toks = head.split()
        if len(toks) < 2:
            # need at least a product-name token + a packing token
            continue
        packing = toks[-1]
        product = " ".join(toks[:-1]).strip()
        if not product:
            continue

        rows.append([
            party,
            area,
            product,
            packing,
            rm.group('qty'),
            rm.group('free'),
            rm.group('rate'),
            rm.group('amt'),
        ])

    return headers, rows
