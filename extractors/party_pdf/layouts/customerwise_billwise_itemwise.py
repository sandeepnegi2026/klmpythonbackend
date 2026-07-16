import re

# ---------------------------------------------------------------------------
# HERITAGE MARKETEERS (Kolar) "Customerwise Billwise Itemwise Report" — KLM
# stockist, one PDF per KLM division/brand.  Modeled on the BlueFox
# `bluefox_customerwise_sales` layout (customer band -> bill/item detail rows),
# but the columns are PRODUCT-FIRST BILLWISE with an explicit Rate column:
#
#   Page furniture (repeats on every page):
#       "HERITAGE MARKETEERS" (vendor) / "KATHA NO ... KOLAR-563101" (address) /
#       "Customerwise Billwise Itemwise Report For Date From ... To ..." (title) /
#       "Bill No Date Item Description Qty Free Rate Value" (column header) /
#       "Report Date : <dd-mm-yyyy> Page <n> of <m>" (page footer).
#
#   Body:
#       <DIVISION band>  "701 KLM-COSMO - DIVISION" / "762 KLM LABS PVT LTD
#                         (COSMOCOR )" — a 3-digit code + KLM<sep>...  (division)
#       <CUSTOMER band>  "008007 K .H MEDICALS,OPP GOVT HIGH SCHOOL BANGARAPET" —
#                         a 5-6 digit account code + "<PARTY>,<address... town>".
#                         The PDF text layer detaches the party's leading letter
#                         ("S IDDHIVINAYAKA", "K .H"); it is rejoined.
#       <detail rows>    "<BillNo> <dd/mm/yy> <Item ...> <Qty> <Free> <Rate>
#                         <Value>" — one item line per bill.
#       "Customer Total <value>"  per-party subtotal (skipped).
#       a bare "<value>" grand-total echo at the end of the file (skipped).
#
# On a few long-product rows the PDF interleaves the Qty digits into the pack
# suffix of the item text ("...LOTION 150ML1 0 296.43", "...150M1L0 1 ..."),
# so the clean "Qty Free Rate Value" tail can't be peeled directly.  Those are
# recovered by de-interleaving the digits that surround the pack unit letters
# ("150M1L0" -> pack "150ML", qty "10") — qty is read from the printed digits,
# NOT synthesised from Value/Rate.
#
# Reconciles EXACTLY: summed Value == the file's bare grand-total echo, which in
# turn equals the sum of every "Customer Total" subtotal (verified on all 7
# division files: COSMO 52563.91, COSMOCOR 133826.47, COSMO Q 1067.79,
# DERMA 156244.74, DERMACOR 131271.66, PEDIA 24361.13, PHARMA 111818.23).
# ---------------------------------------------------------------------------

H = ['Party Name', 'Area', 'Product Name', 'Bill No', 'Bill Date',
     'Qty', 'Free', 'Rate', 'Value']

# Detail row: BillNo, dd/mm/yy(yy), Item, Qty, Free, Rate, Value (clean case).
_ROW = re.compile(
    r'^(\d+)\s+'                    # 1 Bill No
    r'(\d{2}/\d{2}/\d{2,4})\s+'     # 2 Bill Date
    r'(.*?)\s+'                     # 3 Item Description (pack printed inline)
    r'(\d+)\s+'                     # 4 Qty
    r'(\d+)\s+'                     # 5 Free
    r'([\d,]+\.\d{2})\s+'           # 6 Rate
    r'([\d,]+\.\d{2})\s*$'          # 7 Value
)

# Fused-Qty fallback: a detail row whose Qty digit(s) got interleaved into the
# item's pack-unit suffix ("...150ML1 0 296.43 296.43" / "...150M1L0 1 ...").
# Group order after stripping BillNo/Date: <item ... fused-pack> <free> Rate Value
_ROW_FUSED = re.compile(
    r'^(\d+)\s+'                    # 1 Bill No
    r'(\d{2}/\d{2}/\d{2,4})\s+'     # 2 Bill Date
    r'(.*?)\s+'                     # 3 Item (ends in fused pack token)
    r'(\d+)\s+'                     # 4 Free
    r'([\d,]+\.\d{2})\s+'           # 5 Rate
    r'([\d,]+\.\d{2})\s*$'          # 6 Value
)

# Fused pack tail: "<n>M[<d>]L[<d>]" where the digits around the M/L are the Qty
# scrambled into the pack ("150ML1" -> 150ML qty 1; "150M1L0" -> 150ML qty 10).
_FUSED_PACK = re.compile(r'^(\d+)M(\d*)L(\d*)$')

# Division band: "<3-digit code> KLM<sep>..." (KLM-COSMO / KLM LABS / KLM LAB...).
_DIVISION = re.compile(r'^\d{3}\s+KLM[\s\-(]')

# Customer band: "<5-6 digit account code> <PARTY ..., address ... town>".
_CUSTOMER = re.compile(r'^(\d{5,6})\s+(.+)$')

# Party's leading letter is detached by the PDF ("S IDDHIVINAYAKA" / "K .H").
_LEAD_LETTER = re.compile(r'^([A-Z])\s+(\S)')

# Bare grand-total echo lines printed at end of file ("133826.47").
_BARE_MONEY = re.compile(r'^[\d,]+\.\d{2}$')

_FURNITURE = (
    'heritage marketeers', 'katha no', 'customerwise billwise itemwise report',
    'bill no date item description', 'report date', 'customer total',
)


def _split_customer(rest):
    """"<PARTY>,<address ... town>" -> (party, town). The party's leading letter
    is rejoined ('S IDDHIVINAYAKA' -> 'SIDDHIVINAYAKA', 'K .H' -> 'K.H'); the
    town is the last comma-separated field (BlueFox convention)."""
    fields = rest.split(',')
    party = fields[0].strip()
    m = _LEAD_LETTER.match(party)
    if m:
        party = party[0] + party[2:]        # glue detached leading letter
    town = fields[-1].strip() if len(fields) > 1 else ''
    return party, town


def _emit(rows, party, town, item, billno, date, qty, free, rate, value):
    rows.append([
        party, town, item.strip(), billno, date,
        qty, free, rate.replace(',', ''), value.replace(',', ''),
    ])


def parse_customerwise_billwise_itemwise(text):
    rows = []
    party = town = ''
    for ln in text.splitlines():
        s = ln.strip()
        if not s:
            continue
        low = s.lower()
        if any(low.startswith(f) for f in _FURNITURE):
            continue
        if _BARE_MONEY.match(s):
            continue                        # grand-total echo
        if _DIVISION.match(s):
            continue                        # division band (label only)

        # Clean detail row first.
        m = _ROW.match(s)
        if m:
            billno, date, item, qty, free, rate, value = m.groups()
            _emit(rows, party, town, item, billno, date, qty, free, rate, value)
            continue

        # Fused-Qty detail row (Qty scrambled into the item pack tail).
        m = _ROW_FUSED.match(s)
        if m:
            billno, date, item, free, rate, value = m.groups()
            toks = item.split()
            fp = _FUSED_PACK.match(toks[-1]) if toks else None
            if fp:
                lead, d1, d2 = fp.groups()
                qty = (d1 + d2) or '0'
                toks[-1] = lead + 'ML'       # restore clean pack
                _emit(rows, party, town, ' '.join(toks), billno, date,
                      qty, free, rate, value)
                continue

        # Customer band ("<code> <PARTY>,<address town>").
        cm = _CUSTOMER.match(s)
        if cm and ',' in cm.group(2):
            party, town = _split_customer(cm.group(2))
    return H, rows
