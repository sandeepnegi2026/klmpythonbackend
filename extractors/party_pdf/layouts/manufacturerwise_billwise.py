import re

# Business/role words that must never be treated as a town (guards the peel).
_BIZ = {
    "MEDICAL", "MEDICALS", "MEDICOS", "MEDICOSE", "PHARMACY", "PHARMA",
    "STORE", "STORES", "AGENCIES", "AGENCY", "CHEMIST", "CHEMISTS", "MART",
    "SURGICALS", "DISTRIBUTORS", "TRADERS", "ENTERPRISES", "CARE", "AND",
    "CO", "LAB", "DIV", "SU", "UN", "GEN",
}


def _split_town(name):
    """Sri Senthil party bands are "<NAME> <TOWN>" — the town is the LAST token
    (commas here are buried inside doctor qualifications like "MD,DVL.", so a
    comma split is unsafe; a last-token peel is). Cleans trailing '.', pincode
    ("ERODE-638004") and a comma-glued prefix ("ROAD,ERODE" -> ERODE). Guarded so
    a business word or a too-short/numeric token is never peeled."""
    raw = name.strip()
    parts = raw.rsplit(None, 1)
    if len(parts) < 2:
        return raw, ""
    head, last = parts[0], parts[1]
    keep = ""
    if "," in last:                       # "ROAD,ERODE-63800" -> keep "ROAD", town rest
        keep, _, last = last.rpartition(",")
    town = re.sub(r"-\d+$", "", last.strip().strip(".").strip()).strip()
    if not re.fullmatch(r"[A-Za-z][A-Za-z .]*", town) or town.upper() in _BIZ or len(town) < 3:
        return raw, ""
    name_clean = (head + " " + keep).strip().rstrip(" ,.-").strip()
    return (name_clean or raw), town


def parse_manufacturerwise_billwise(text):
    """Sri Senthil 'Manufacturerwise Sales Report' billwise layout.

    The extracted raw text repeats the ENTIRE report once per printed page
    (N pages -> N identical copies), so we keep only the first complete copy:
    everything up to and including the first 'Division Sub Total' (the final
    grand-total line). Within that copy:
      - bare non-numeric, non-structural lines are PARTY headings (injected
        into every following data row),
      - data rows start with a DATE (dd/mm/yy) then a bill no, a product name,
        then a VARIABLE count of numbers. The trailing 4 numbers are always
        Gross, Rate, MRP, Repl(Val); the leading 1-3 numbers are Qty [Free]
        [R Qty] (free / r-qty omitted when zero). Amount maps to Gross.
    """
    NUM = r'-?\d+(?:\.\d+)?'
    DATE_RE = re.compile(r'^(\d{2}/\d{2}/\d{2})\s+(\S+)\s+(.*)$')

    headers = ["Party Name", "Area", "Date", "Inv No", "Product Name",
               "Qty", "Free", "Gross", "Rate", "MRP", "Repl", "Amount"]

    lines = text.splitlines()

    # De-duplicate the per-page repetition: stop at the first grand-total line.
    cut = None
    for i, l in enumerate(lines):
        if l.strip().lower().startswith('division sub total'):
            cut = i
            break
    if cut is not None:
        lines = lines[:cut + 1]

    rows = []
    party = None
    party_area = ''
    for raw in lines:
        s = raw.strip()
        if not s:
            continue
        low = s.lower()

        # structural / non-data lines
        if s.startswith('---') or 'manufacturerwise sales report' in low:
            continue
        if (low.startswith('bill date')
                or low.startswith('product sub tot')
                or low.startswith('division sub total')):
            continue
        if low.startswith('from ') and ' to ' in low:
            continue

        m = DATE_RE.match(s)
        if m:
            date, billno, rest = m.group(1), m.group(2), m.group(3)
            nums = re.findall(NUM, rest)
            if len(nums) < 4:
                # not a real data row (need at least Gross,Rate,MRP,Repl)
                continue
            first = re.search(NUM, rest)
            prod = rest[:first.start()].strip()
            # GATED: a number embedded INSIDE the product name ("EKRAN 80
            # HYDRA 1 576.43 ...") must not be stolen into Qty. Anchor on the
            # maximal TRAILING run of purely-numeric tokens; re-split there
            # only when it disagrees with the regex scan (defect signature).
            toks = rest.split()
            k = len(toks)
            while k > 0 and re.fullmatch(NUM, toks[k - 1]):
                k -= 1
            tail = toks[k:]
            if len(tail) >= 4 and len(tail) != len(nums):
                nums = tail
                prod = ' '.join(toks[:k]).strip()
            # trailing four fixed columns
            gross, rate, mrp, repl = nums[-4], nums[-3], nums[-2], nums[-1]
            lead = nums[:-4]                      # Qty [Free] [R Qty]
            # GATED: a return-only bill line has a blank Qty AND a blank Gross
            # (only R Qty + Rate/MRP/Repl printed), so exactly 4 numbers survive
            # and the lone R-Qty integer masquerades as Gross. A real Gross is
            # always a decimal (Rate*Qty) while R Qty is a bare integer -- so
            # when there is no lead column and the would-be Gross carries no
            # decimal point, it is actually R Qty: Gross/amount is nil and the
            # integer belongs in the R-Qty (free) slot, not in amount.
            if not lead and '.' not in gross:
                free_rqty = gross
                gross = ''
                qty = ''
                free = free_rqty
            else:
                qty = lead[0] if len(lead) >= 1 else ''
                free = lead[1] if len(lead) >= 2 else ''
            rows.append([party or '', party_area, date, billno, prod,
                         qty, free, gross, rate, mrp, repl, gross])
            continue

        # bare numeric lines (page sub/grand totals) -> ignore, keep party
        if re.fullmatch(r'[\d\s.\-]+', s):
            continue

        # otherwise this is a party heading.
        # GATED: the manufacturer/division heading can be printed fused onto
        # the first party band line ("KLM LABS,-DERMA DIV  AVIS PHARMA,
        # ERODE.") -- keep only the party segment after the "...LABS...DIV"
        # prefix. Fires only when a \bLABS\b token precedes a \bDIV token.
        mdiv = re.match(r'^(.*?\bDIV)\s+(\S.*)$', s)
        if mdiv and re.search(r'\bLABS\b', mdiv.group(1)):
            s = mdiv.group(2).strip()
        party, party_area = _split_town(s)

    return headers, rows