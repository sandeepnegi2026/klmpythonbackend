import re

def parse_companywise_customerwise(text):
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