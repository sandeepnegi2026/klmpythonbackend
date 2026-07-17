import re

# ---------------------------------------------------------------------------
# "Area Wise Sales Report for the period of <ISO> and <ISO>" (VASAVI MEDICARE
# SOLUTIONS, Coimbatore) — KLM sub-stockist.
#
# Column header:
#   Sr. Code Product Name Packing Batch No. Qty FQty Sch % Rate Item Value
#   Exp. Date Amount Invoice No. Inv. Date
#
# Body = "<CUSTCODE> - <PARTY NAME>, <AREA>-<PIN>" band -> "KLM LABORA - KLM"
# company sub-band (3-letter code: never matches the party-band shape) ->
# numbered invoice rows -> "Total of KLM LABORA : <iv> <amt>" -> final
# "Grand Total : <iv> <amt>".
#
# Item row (right-anchored — Exp.Date / Inv.Date are dd-mm-yyyy):
#   <Sr> <PRODcode> <Product ... Packing Batch> <Qty> <FQty> <Sch%> <Rate>
#   <ItemValue> <ExpDate> <Amount> <InvoiceNo> <InvDate>
# The Packing and Batch cells print glued to the product text; the trailing
# batch token (alnum-with-digits) is peeled off.
#
# Reconciles EXACTLY against the printed "Grand Total : 58,404.55 64,280.28"
# (summed Amount) on the reference file.
# ---------------------------------------------------------------------------

H = ['Party Name', 'Area', 'Product Name', 'Qty', 'Free', 'Rate', 'Amount',
     'Bill No', 'Bill Date']

_ROW = re.compile(
    r'^(\d+)\s+'                          # 1 Sr
    r'(\S*\d\S*)\s+'                      # 2 product code (PROD690)
    r'(.+?)\s+'                           # 3 product text (+packing+batch)
    r'([\d,]+\.\d+)\s+'                   # 4 Qty
    r'([\d,]+\.\d+)\s+'                   # 5 FQty
    r'([\d,]+\.\d+)\s+'                   # 6 Sch %
    r'([\d,]+\.\d+)\s+'                   # 7 Rate
    r'([\d,]+\.\d+)\s+'                   # 8 Item Value
    r'(\d{2}-\d{2}-\d{4})\s+'             # 9 Exp. Date
    r'([\d,]+\.\d+)\s+'                   # 10 Amount
    r'(\S+)\s+'                           # 11 Invoice No
    r'(\d{2}-\d{2}-\d{4})\s*$'            # 12 Inv. Date
)

_BAND = re.compile(r'^([A-Z]{4,8})\s+-\s+(.+)$')
_PIN = re.compile(r'[-\s]*\d{6}\s*$')
_BATCH = re.compile(r'^[A-Z0-9][A-Z0-9/-]*\d[A-Z0-9/-]*$')


def _num(t):
    return t.replace(',', '')


def parse_areawise_sales_period(text):
    rows = []
    party = area = ''
    for ln in text.splitlines():
        s = ln.strip()
        if not s or s.lower().startswith(('total of', 'grand total', 'page ', 'sr. code')):
            continue
        m = _ROW.match(s)
        if m:
            (_sr, _pcode, prod, qty, fqty, _sch, rate, _iv,
             _exp, amt, invno, invdate) = m.groups()
            toks = prod.split()
            if len(toks) > 1 and _BATCH.match(toks[-1]) and any(c.isalpha() for c in toks[-1]):
                toks = toks[:-1]              # peel the batch token
            rows.append([
                party, area, " ".join(toks),
                _num(qty), _num(fqty), _num(rate), _num(amt), invno, invdate,
            ])
            continue
        bm = _BAND.match(s)
        if bm and (',' in bm.group(2) or _PIN.search(bm.group(2))):
            tail = bm.group(2)
            if ',' in tail:
                name, ar = tail.rsplit(',', 1)
            else:
                name, ar = tail, ''
            party = name.strip()
            area = _PIN.sub('', ar.strip()).strip(' -.')
    return H, rows
