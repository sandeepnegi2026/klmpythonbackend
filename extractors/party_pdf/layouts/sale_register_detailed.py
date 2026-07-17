import re

# ---------------------------------------------------------------------------
# "SALE REGISTER DETAILED FROM <date> TO <date>" (VIJAY MEDICAL AGENCIES,
# Jassur) — Marg billwise register.
#
# Column header (wrapped):
#   SNO. BILL DATE BILL NO. ITEM NAME [PACK/GRADE] LOT NO. TOTAL QTY [FREE QTY]
#   RATE/UNIT NET AMOUNT
#
# Body = "PARTY NAME - <NAME>[-<TOWN>]" band -> item rows -> "Date Totals"
# lines -> final "Grand Totals <qty> <free> <amount>".
#
# Item row: <SNO> [<dd/mm/yyyy>] [<BILLNO e.g. VGST-620>] <item ... lot>
#           <qty> [<free>] <rate:4dp> <amount>
# The bill DATE prints only on the first bill of each date and the BILL NO.
# only on the first item of each bill — both carry forward. Qty/free can be
# fractional ("12.5", ".5"). RATE always prints 4 decimals, which anchors the
# split between the optional free and the amount.
#
# Reconciles EXACTLY against the printed "Grand Totals 330 48 91,544.85" on
# the reference file (its stock twin's NET SALE total is the same 330).
# ---------------------------------------------------------------------------

H = ['Party Name', 'Area', 'Product Name', 'Bill No', 'Bill Date',
     'Qty', 'Free', 'Rate', 'Amount']

_QTY = r'(?:\d+(?:\.\d+)?|\.\d+)'

_ROW = re.compile(
    r'^(\d+)\s+'                          # 1 SNO
    r'(?:(\d{2}/\d{2}/\d{4})\s+)?'        # 2 bill date (first bill of the day)
    r'(?:([A-Z][A-Z0-9]*-\d+)\s+)?'       # 3 bill no   (first item of the bill)
    r'(.+?)\s+'                           # 4 item text (+lot glued at tail)
    r'(' + _QTY + r')\s+'                 # 5 qty
    r'(?:(' + _QTY + r')\s+)?'            # 6 free
    r'(\d+\.\d{4})\s+'                    # 7 rate (always 4dp)
    r'([\d,]+\.\d{2})\s*$'                # 8 net amount
)

_PARTY = re.compile(r'^PARTY NAME\s*-\s*(.+)$', re.I)

# trailing lot/batch token: alnum with digits, >=4 chars, not a pack ("1*10",
# "50GM", "10'S")
_LOT = re.compile(r"^[A-Z0-9][A-Z0-9/-]*\d[A-Z0-9/-]*$")
_PACKISH = re.compile(r"(\d+\*\d+|GM|ML|MG|KG|'S|TAB|CAP)$", re.I)


def _split_party(s):
    s = s.strip()
    if '-' in s:
        name, town = s.rsplit('-', 1)
        town = town.strip()
        if town and ' ' not in town and not any(ch.isdigit() for ch in town):
            return name.strip(' -'), town
    return s, ''


def parse_sale_register_detailed(text):
    rows = []
    party = area = ''
    cur_date = cur_bill = ''
    for ln in text.splitlines():
        s = ln.strip()
        if not s:
            continue
        pm = _PARTY.match(s)
        if pm:
            party, area = _split_party(pm.group(1))
            continue
        low = s.lower()
        if low.startswith(('date totals', 'grand totals', 'sno.', 'page no', 'printed by')):
            continue
        m = _ROW.match(s)
        if not m:
            continue
        _sno, date, bill, item, qty, free, rate, amt = m.groups()
        if date:
            cur_date = date
        if bill:
            cur_bill = bill
        toks = item.split()
        if len(toks) > 1 and _LOT.match(toks[-1]) and len(toks[-1]) >= 4 \
                and not _PACKISH.search(toks[-1]):
            toks = toks[:-1]                 # peel the lot/batch token
        rows.append([
            party, area, " ".join(toks), cur_bill, cur_date,
            qty, free or '0', rate, amt.replace(',', ''),
        ])
    return H, rows
