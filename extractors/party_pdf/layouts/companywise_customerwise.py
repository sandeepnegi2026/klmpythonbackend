import re

def parse_companywise_customerwise(text):
    headers, rows = _parse_ccode(text)
    if rows:
        return headers, rows
    # Numeric-code variant (e.g. DELTA PHARMA / KLM COSMO DIV): both the customer
    # code and the item code are purely numeric (029004, 173007) instead of the
    # C#####/[A-Z]##### the C-code path keys on, and the customer header carries a
    # run of glued phone numbers with the town stuck to the last one
    # ("...8086160038MARADU P.O"). Reached ONLY when the C-code path extracted
    # nothing, so every file that already parses is byte-for-byte unaffected.
    return _parse_numeric(text)


_NUM_SKIP_PREFIXES = (
    'company:', 'report date', 'item sale qty', 'companywise', 'total sale value',
)


def _town_from_tail(tail):
    """The town is glued onto the last phone digit-block in the customer header
    ("...9847938330PALLIMUKKU EKM"). Take the alphabetic run that begins right
    after the FINAL digit-then-letter boundary; that skips messy/OCR'd phone
    fragments earlier in the line and keeps only the trailing town."""
    tail = tail.strip()
    if not tail:
        return ""
    positions = [mm.start() for mm in re.finditer(r'\d(?=[A-Za-z])', tail)]
    if positions:
        return tail[positions[-1] + 1:].strip()
    m = re.search(r'([A-Za-z][A-Za-z .()\-]*)$', tail)
    return m.group(1).strip() if m else ""


def _parse_numeric(text):
    headers = ["Party Name", "Area", "Product Name", "Qty", "Free", "Amount"]
    rows = []
    cur_party = None
    cur_area = ""
    # Item: <numeric code> <product name> <SaleQty:int> <Sch.Qty:int> <SalVal:money>
    item_re = re.compile(r'^(\d{3,6})\s+(.*?)\s+(\d+)\s+(\d+)\s+([\d,]+\.\d{2})\s*$')
    # Glued variant: SaleQty stuck to the product's trailing pack unit with no
    # space ("...LOTION 150ML10 4 2,964.30"). Split at the last alpha->digit
    # boundary so the pack ("150ML") stays with the name and "10" is the qty.
    # Only reached when the spaced pattern fails, so normal rows are unaffected.
    item_glued_re = re.compile(r'^(\d{3,6})\s+(.*?[A-Za-z])(\d+)\s+(\d+)\s+([\d,]+\.\d{2})\s*$')
    subtotal_re = re.compile(r'^[\d,]+\.\d{2}$')
    # Customer header: <NAME> <CODE:4-6 digits> <phone/town noise>. Starts with a
    # letter (item lines start with a digit and are consumed above first), so the
    # address line ("38/1044, ...") and bare-number lines never match here.
    party_re = re.compile(r'^([A-Za-z].*?)\s+(\d{4,6})\b(.*)$')
    for ln in text.splitlines():
        s = ln.strip()
        if not s:
            continue
        low = s.lower()
        if low.startswith(_NUM_SKIP_PREFIXES):
            continue
        m = item_re.match(s) or item_glued_re.match(s)
        if m:
            if cur_party:
                rows.append([cur_party, cur_area, m.group(2).strip(),
                             m.group(3), m.group(4), m.group(5).replace(',', '')])
            continue
        if subtotal_re.match(s):
            continue
        p = party_re.match(s)
        if p:
            cur_party = p.group(1).strip()
            cur_area = _town_from_tail(p.group(3))
            continue
    return headers, rows


def _parse_ccode(text):
    headers = ["Party Name", "Area", "Product Name", "Qty", "Free", "Amount"]
    rows = []
    cur_party = None
    cur_area = ""
    # Item line: I##### PRODUCT NAME  SaleQty  Sch.Qty  SalVal
    item_re = re.compile(r'^([A-Z]\d{4,6})\s+(.*?)\s+(\d+)\s+(\d+)\s+([\d,]+\.\d{2})\s*$')
    # Customer header: <NAME ...> [flags/tags] C##### <phones/area noise> <AREA>.
    # Between the name and the C-code the ERP prints account-type junk: a single
    # char flag ($, #, *) and/or a bracketed GST tag ("[GST]", "[ NON GST]"),
    # in any order and glued to either side ("NAME $ C001", "NAME #C001",
    # "NAME $ [GST] C001", "NAME $[GST]C001"). The repeatable non-capturing group
    # consumes all of it so none lands in party_name; matching \s* (not \s+)
    # before the code also recovers headers whose code is glued onto the
    # name/flag ("...STORESC05325"). Only junk immediately preceding the code is
    # stripped — a bracket/flag elsewhere in the name is preserved.
    # (the \[[A-Z ]{1,8} alt catches a malformed/truncated unclosed tag like
    # "[N" the ERP occasionally emits; bounded to letters/spaces so it can never
    # swallow the C-code.)
    cust_re = re.compile(
        r'^(.*?)(?:\s*(?:[$#*]|\[[^\]]*\]|\[[A-Z ]{1,8}))*\s*(C\d{4,6})\b\s*(.*)$'
    )
    subtotal_re = re.compile(r'^[\d,]+\.\d{2}$')

    for ln in text.splitlines():
        s = ln.strip()
        if not s:
            continue
        low = s.lower()
        if (low.startswith('company:') or low.startswith('report date') or
                low.startswith('item sale qty') or low.startswith('companywise') or
                low.startswith('total sale value') or low.startswith('ward no') or
                s == 'RAJESH MEDICOSE'):
            continue
        m = item_re.match(s)
        if m:
            if cur_party:
                rows.append([cur_party, cur_area, m.group(2).strip(),
                             m.group(3), m.group(4), m.group(5).replace(',', '')])
            continue
        # standalone per-customer subtotal line (just a number) -> skip
        if subtotal_re.match(s):
            continue
        c = cust_re.match(s)
        if c:
            cur_party = c.group(1).strip()
            tail = c.group(3).strip()
            area = ""
            am = re.search(r'([A-Z][A-Z0-9 ()\-]*)$', tail)
            if am:
                area = am.group(1).strip()
            cur_area = area
            continue
    return headers, rows