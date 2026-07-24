import re

# KOOTTIPARAMBIL COMBINES / AYYAPPA ENTERPRISES "Customerwise Itemwise Billwise
# Sales Report".
#
# Monospaced export. Structure:
#   <SHOP NAME> / address line
#   Customerwise Itemwise Billwise Sales Report For Date From <d> To <d>
#   Bill No Ref ID Date Item Description QtyFree Rate MRP ValuePur.Rate Pur.Value
#   <CompCode> KLM <DIVISION>(<beat>)             <- company/division band (has "KLM")
#   <CustCode> <NAME>,<TOWN> <AREA>               <- customer band (has a comma)
#   <BillNo> <DD/MM/YY><Item...> <Sch> <Qty> <Free> <Rate> <MRP> <Value> <PurRate> <PurValue>
#   ...
#   Customer Total <value> <purvalue>             <- per-customer footer (oracle)
#   ...
#   <grand value> <grand purvalue>                <- bare grand-total line(s)
#   Report Date : ...
#
# Column peel is anchored on the LAST FIVE *decimal* numbers (Rate MRP Value
# Pur.Rate Pur.Value are ALWAYS printed with a decimal point, e.g. '213.560',
# '266.95'); Sch/Qty/Free are bare integers printed BEFORE them. So:
#   Value = 3rd-from-last decimal  (the reconcile column; sum == Customer Total
#           == the printed grand total, EXACT on every clean file)
#   Rate  = 5th-from-last decimal.
# Value == Qty*Rate on every row, so Qty is DERIVED as round(Value/Rate); this also
# recovers the AYYAPPA glyph-mangled rows where the bare Qty/Free were corrupted
# into the item text ('...BROW1N) 600GM1,050.850 ...') and only the 5 decimals
# survive — Value is still the 3rd-from-last decimal, so no row (or value) drops.
# The date is glued to the item's first word ('12/06/26KOJITIN'); it is split off.

# a decimal money/rate token (must carry a '.')
_DEC = r"-?\d[\d,]*\.\d+"
# the trailing run of five space-separated decimals (rate mrp value purrate purvalue);
# the first (rate) may be glued to a pack token, so no left word-boundary is required.
_TAIL5 = re.compile(r"(?:" + _DEC + r"\s+){4}" + _DEC + r"\s*$")

# item/bill row: <billno> <dd/mm/yy><item glued...>
_ROW_RE = re.compile(r"^(?P<bill>\d{3,})\s+(?P<date>\d{2}/\d{2}/\d{2})(?P<rest>.+)$")

# company/division band: <code> KLM <division> (no date, contains 'KLM')
_COMP_RE = re.compile(r"^\d{1,5}\s+KLM\b", re.I)
# customer band: <code> <name>,<town> <area> (code is digits or 2-letter+digits;
# body carries a comma). Anything with 'KLM(' or a date is NOT a customer band.
_CUST_RE = re.compile(r"^(?P<code>[A-Za-z]{0,3}\d{3,})\s+(?P<body>.+,.+)$")

_SKIP_RE = re.compile(
    r"^\s*("
    r"Customer\s+Total\b"
    r"|Report\s+Date\b"
    r"|Bill\s+No\s+Ref\s+ID\b"
    r"|Customerwise\s+Itemwise\s+Billwise\b"
    r"|[\d,]+\.\d+\s+[\d,]+\.\d+\s*$"      # bare grand-total line(s)
    r")", re.I)


def _peel_ints(s, limit=3):
    """Peel up to `limit` trailing pure-integer tokens off s. Returns
    (remainder, ints_in_reading_order). Stops at the first non-integer token so
    a pack unit ('GM') or an alnum item token ('60K') halts the peel."""
    toks = s.split()
    ints = []
    while toks and len(ints) < limit and re.fullmatch(r"\d+", toks[-1]):
        ints.insert(0, toks.pop())
    return " ".join(toks), ints


def parse_customerwise_itemwise_billwise(text):
    headers = ["Party Name", "Area", "Product Name", "Bill No",
               "Invoice Date", "Qty", "Free", "Rate", "Amount"]
    rows = []
    party = ""
    loc = ""

    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            continue

        rm = _ROW_RE.match(s)
        if rm and _TAIL5.search(rm.group("rest")):
            rest = rm.group("rest")
            mt = _TAIL5.search(rest)
            decs = re.findall(_DEC, rest[mt.start():])
            # rate mrp value purrate purvalue
            rate = decs[-5].replace(",", "")
            value = decs[-3]
            # item + optional bare Sch/Qty/Free precede the 5-decimal tail
            head = rest[:mt.start()].strip()
            head, ints = _peel_ints(head, limit=3)
            free = ints[-1] if ints else "0"
            try:
                rf = float(rate)
                qty = str(int(round(float(value.replace(",", "")) / rf))) if rf else "0"
            except (ValueError, ZeroDivisionError):
                qty = ints[-2] if len(ints) >= 2 else "0"
            product = head.strip()
            if not product or not party:
                continue
            rows.append([party, loc, product, rm.group("bill"),
                         rm.group("date"), qty, free, rate, value])
            continue

        if _SKIP_RE.match(s):
            continue

        if _COMP_RE.match(s):
            # company/division band — context only; do not reset party
            continue

        cm = _CUST_RE.match(s)
        if cm:
            body = cm.group("body")
            name, _, rest_loc = body.partition(",")
            party = name.strip()
            loc = rest_loc.strip()
            continue

        # address / noise — ignore, keep current party

    return headers, rows
