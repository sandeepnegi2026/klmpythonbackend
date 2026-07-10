import re

# ---------------------------------------------------------------------------
# "Customer-Wise Product-Wise Sales Summary" (MAHESH AGENCIES, Wardha) — KLM
# stockist. NOT the Unisolve billwise export (whose title-gate also matches
# "customer-wise product-wise"): here rows are per-product aggregates under a
# coded customer band, with no bill numbers at all.
#
# Furniture per page:
#   <VENDOR> Printed On: <date> / "Customer-Wise Product-Wise Sales Summary
#   From : ... To : ..." / "Agency : [1021] KLM LABORATORIES PVT. LTD" /
#   dashes / "Code Customer Name & City Prd.Code Product Name Pack Qty Free
#   Value" / dashes.
#
# Body:
#   <Code> <CUSTOMER NAME>,<CITY> <PrdCode> <Product [Pack]> <Qty> <Free|-> <Value>
#   <PrdCode> <Product [Pack]> <Qty> <Free|-> <Value>        (continuation)
#   "Total : <amt>" between customers; final "Total Value : <amt>".
# The band row carries its FIRST product inline. Customer code is letters+digits
# ("A004", "Y106"); product code is a long all-digit run (10210035), so the two
# row shapes cannot collide. Free prints "-" when zero.
#
# Reconciles EXACTLY: summed Value = the printed "Total Value : 399365.64" on
# the reference file (which also matches the vendor's own stock report footer
# "Sales Value 3,99,365.64").
# ---------------------------------------------------------------------------

H = ['Party Name', 'Area', 'Product Name', 'Qty', 'Free', 'Amount']

_TAIL = (
    r'(\d{6,10})\s+'            # product code (anchors the split)
    r'(.+?)\s+'                 # product name (+pack glued)
    r'(\d+)\s+'                 # qty
    r'(\d+|-)\s+'               # free ('-' when zero)
    r'([\d,]+\.\d{2})\s*$'      # value
)

_BAND = re.compile(r'^([A-Z]{1,3}\d{2,5})\s+(.+?)\s+' + _TAIL)
_CONT = re.compile(r'^' + _TAIL)


def _split_name_city(s):
    s = s.strip()
    if ',' in s:
        name, city = s.rsplit(',', 1)
        return name.strip(), city.strip(' .')
    return s, ''


def parse_customer_product_wise_summary(text):
    rows = []
    party = area = ''
    for ln in text.splitlines():
        s = ln.strip()
        if not s or s.startswith('-') or s.lower().startswith('total'):
            continue
        m = _BAND.match(s)
        if m:
            _code, namecity, _pcode, prod, qty, free, val = m.groups()
            party, area = _split_name_city(namecity)
        else:
            m = _CONT.match(s)
            if not m:
                continue
            _pcode, prod, qty, free, val = m.groups()
            if not party:
                continue
        rows.append([
            party, area, prod.strip(),
            qty, '0' if free == '-' else free, val.replace(',', ''),
        ])
    return H, rows
