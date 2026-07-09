import re

def parse_shree_nath_billwise(text):
    """SHREE NATH ENTERPRISE billwise layout.
    Heading 'SHREE NATH ENTERPRISE', date range, then header
    'Bill No Date Product NamQtey Qty.Fr. Sch.Qty Rate L.Rate Qty X Rate'.
    Each party is a bare UPPERCASE heading line; its detail rows start with a
    bill no like 'A/753', followed by a date and a (text-mangled) product name
    plus trailing numeric columns. The LAST trailing numeric token is the
    'Qty X Rate' line amount; the 3rd-from-last is Rate. 'Total' lines are
    cumulative running totals and are skipped. The qty digit fuses into the
    product-name string, so Qty is recovered as amount/rate; Free ('Qty.Fr.')
    is read from its structural slot (5th-from-last trailing numeric) or from
    the digit interleaved into the '<n>ML' pack token ('200M2L' = free 2);
    Amount (the reconciled field) is exact."""
    headers = ["Party Name", "Inv No", "Date", "Product Name",
               "Qty", "Free", "Rate", "Amount"]
    rows = []
    party = None
    DATE_RE = re.compile(r'\d{1,2}/\d{1,2}/\d{4}')
    BILL_RE = re.compile(r'^([A-Za-z]{1,4}/\d+)\b')
    NUM_RE = re.compile(r'\d+(?:\.\d+)?$')

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        low = line.lower()
        # structural / total lines
        if (low.startswith('bill no') or low.startswith('from ')
                or low == 'amount' or low.startswith('grand total')
                or low.startswith('total')):
            continue

        m = BILL_RE.match(line)
        if m:
            bill = m.group(1)
            rest = line[m.end():].strip()
            date = ''
            after = rest
            dm = DATE_RE.search(rest)
            if dm:
                date = dm.group(0)
                after = rest[dm.end():].strip()
            toks = after.split()
            # collect the trailing run of purely-numeric tokens
            i = len(toks) - 1
            nums = []
            while i >= 0 and re.fullmatch(r'\d+(?:\.\d+)?', toks[i]):
                nums.insert(0, toks[i])
                i -= 1
            amount = nums[-1] if nums else ''
            rate = nums[-3] if len(nums) >= 3 else ''
            product = " ".join(toks[:i + 1])
            # Qty digit fuses into the product-name text and can't be read
            # reliably, but this report's amount column IS "Qty X Rate", so qty
            # is recovered exactly as amount/rate. Only fill on a clean integer
            # division (never fabricate a value on a non-clean quotient).
            qty = ''
            try:
                r = float(rate); a = float(amount)
                if r > 0:
                    q = a / r
                    qr = round(q)
                    if qr >= 0 and abs(q - qr) <= 0.02:
                        qty = str(qr)
            except (ValueError, TypeError):
                pass
            # 'Qty.Fr.' free column. Two exact signatures of this report's
            # column fusion (gated so any other mangling leaves free blank,
            # exactly as before):
            #   * pack token stayed clean -> the trailing numeric run holds
            #     [..., Free, Sch.Qty, Rate, L.Rate, Qty X Rate], so free is
            #     the integer 5th-from-last numeric (same positional logic as
            #     rate = nums[-3] above);
            #   * columns fused -> the free digit is interleaved into the
            #     '<n>ML' pack token that broke the numeric run, e.g.
            #     '200M2L' = pack 200ML + free 2 ('200M0L' = free 0).
            free = ''
            if len(nums) >= 5 and re.fullmatch(r'\d+', nums[-5]):
                free = nums[-5]
            elif i >= 0:
                fm = re.fullmatch(r'(\d+)M(\d+)L', toks[i])
                if fm:
                    free = fm.group(2)
            rows.append([party or '', bill, date, product, qty, free, rate, amount])
        else:
            # party heading: has letters, no date, not a pure-number line
            if (not DATE_RE.search(line) and re.search(r'[A-Za-z]', line)
                    and not re.match(r'^[\d.\s]+$', line)):
                party = line

    return headers, rows