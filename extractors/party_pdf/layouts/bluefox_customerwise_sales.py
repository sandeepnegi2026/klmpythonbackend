import re

# ---------------------------------------------------------------------------
# BlueFox Systems "Customerwise Sales Statement on <Month>/<Year>" — KLM
# sub-stockist (FATIMA HEALTHCARE, Manjeri), one file per KLM division.
#
# Page furniture (repeats on EVERY page):
#   <VENDOR NAME> / <address line> / <address line> /
#   "Customerwise Sales Statement on May/2026" / "Company : KLM COSMO" /
#   column header "Bill Date Bill No Product Packing QTY FREE Amount".
#
# Body = "<PARTY NAME>,<TOWN>" heading -> bill rows -> a bare per-party
# subtotal ("<qty> [<free>] <amount>") -> ... -> a final bare grand-total
# line -> "Exported By : ..." / "Software @BlueFox Systems ..." footer.
#
# Bill row (single text line, space-delimited; FREE is BLANK when zero):
#   <dd/mm/yyyy> <BillNo> <Product ... Packing> <Qty:int> [<Free:int>] <Amount>
# The Packing column prints glued as the trailing token of the product text
# ("KOJITIN EMUL GEL 15gm"), so it is peeled by a unit-suffix match.
#
# The heading state machine is armed by the column-header line and disarmed by
# the report-title line, so the per-page address preamble (which contains
# commas and would otherwise look like a "<name>,<town>" heading) can never
# become a party. Bare numeric subtotal/total lines are skipped by shape.
#
# Reconciles EXACTLY against the printed grand total on the reference file
# (KLM COSMO May-2026: qty 71, free 6, amount 31,774.01 — also cross-checks
# the division's stock statement "Sal.Val(PTR+Tax) : 31774.01").
# ---------------------------------------------------------------------------

H = ['Party Name', 'Area', 'Product Name', 'Packing', 'Bill No', 'Bill Date',
     'Qty', 'Free', 'Amount']

_ROW = re.compile(
    r'^(\d{2}/\d{2}/\d{4})\s+'      # 1 Bill Date
    r'(\d+)\s+'                     # 2 Bill No
    r'(.*?)\s+'                     # 3 Product text (packing glued at tail)
    r'(\d+)'                        # 4 Qty
    r'(?:\s+(\d+))?\s+'             # 5 Free (blank when zero)
    r'([\d,]+\.\d+)\s*$'            # 6 Amount
)

# bare per-party subtotal / grand total: "<qty> [<free>] <amount>"
_SUBTOTAL = re.compile(r'^\d+(?:\s+\d+)?\s+[\d,]+\.\d+$')

_PACK = re.compile(r'(\d+(?:\.\d+)?\s*(?:gm|gms|g|mg|kg|ml|mls|l|lt)\.?)$', re.I)

_PIN = re.compile(r'(?:,?\s*PIN\s*:\s*\d+|[-\s]+\d{3}\s*\d{3})\s*$', re.I)

_FURNITURE = (
    'company :', 'bill date bill no', 'exported by', 'software @',
    'page ', 'printed ',
)


def _split_heading(s):
    """"<PARTY NAME>,<TOWN>[ - <pin>|,PIN:<pin>]" -> (party, town)."""
    if ',' not in s:
        return s.strip(' .'), ''
    name, town = s.split(',', 1)
    town = _PIN.sub('', town.strip())
    town = town.split(',', 1)[0].strip(' .-')
    return name.strip(' .'), town


def parse_bluefox_customerwise_sales(text):
    rows = []
    party = area = ''
    armed = False
    for ln in text.splitlines():
        s = ln.strip()
        if not s:
            continue
        low = s.lower()
        if 'customerwise sales statement on' in low:
            armed = False          # page preamble started (address lines follow)
            continue
        if low.startswith('bill date') and 'amount' in low:
            armed = True           # column header — body follows
            continue
        if any(low.startswith(f) for f in _FURNITURE):
            continue
        if not armed:
            continue
        if _SUBTOTAL.match(s):
            continue               # per-party subtotal / grand total
        m = _ROW.match(s)
        if m:
            date, billno, prod, qty, free, amt = m.groups()
            prod = prod.strip()
            pack = ''
            pm = _PACK.search(prod)
            if pm and pm.start() > 0:
                pack = pm.group(1).strip()
                prod = prod[:pm.start()].strip()
            rows.append([
                party, area, prod, pack, billno, date,
                qty, free or '0', amt.replace(',', ''),
            ])
            continue
        if re.search(r'[A-Za-z]', s):
            party, area = _split_heading(s)
    return H, rows
