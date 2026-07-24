import re


def _split_dp_party(heading):
    """Split a SwilERP "Customer-Product wise Sales" heading of the form
    "<CODE>-<NAME>,<TOWN>[,(phone)]" into (name, town). The town is the first
    comma-segment after the name; trailing phone/paren junk is dropped.

    FIX (SATYAM): the CODE segment (before the first '-') may itself contain
    commas/dots (e.g. "AM..,-ABHISHEK MEDICAL,DHANBAD", "MC,.-MAYALOK MEDICAL").
    A naive first-comma split then truncates the code and drops the name. Anchor
    the town split at the first comma at/after the first '-' so the code is kept
    whole and the town is the first comma-segment following the name. Falls back
    to (heading, "") when there's no comma-after-dash or no letter-bearing town."""
    s = heading.strip()
    if "," not in s:
        return s, ""
    dash = s.find("-")
    csearch = dash if dash != -1 else 0
    ci = s.find(",", csearch)
    if ci == -1:
        return s, ""
    name = s[:ci].strip()
    tail = s[ci + 1:]
    town = tail.split(",")[0]
    town = re.sub(r"\(.*$", "", town).strip().strip(" ,()")
    if not re.search(r"[A-Za-z]", town):
        return (name or s), ""
    return (name or s), town


# Business/entity/role words that are never a town (guards the bare-trailing-word
# promotion in Layout B below).
_BIZ_SKIP = {
    "MEDICAL", "MEDICALS", "MEDICOS", "MEDICOSE", "MEDICO", "PHARMA",
    "PHARMACY", "STORE", "STORES", "CHEMIST", "CHEMISTS", "HALL", "CLINIC",
    "HOSPITAL", "HEALTHMART", "SURGICAL", "SURGICALS", "AGENCY", "AGENCIES",
    "DISTRIBUTORS", "ENTERPRISES", "TRADERS", "CO", "COMPANY", "HUF", "STAFF",
    "LAB", "GENERAL", "GEN", "AND", "SKIN", "CARE", "MART", "HUB",
}


def _bracket_town(s):
    """Return (name_without_bracket, town) using the LAST (...)/{...} group of a
    customer heading, or None when there is no closed bracket group. The bracket
    contents are the town by this ERP's convention (e.g. "...(ZIRAKPUR)")."""
    m = None
    for mm in re.finditer(r"[\(\{]\s*([^\(\)\{\}]+?)\s*[\)\}]", s):
        m = mm
    if not m:
        return None
    town = m.group(1).strip()
    clean = re.sub(r"\s{2,}", " ", (s[: m.start()] + " " + s[m.end():])).strip(" -,")
    return (clean or s), town


def _split_b_party(s, known_towns):
    """Split a Layout-B "CUSTOMER:" heading into (name, town). Town comes from the
    last bracket group when present; otherwise a bare trailing word is promoted
    ONLY when the same document parenthesises that exact town elsewhere (so a town
    is never invented and a real name word is never mistaken for one)."""
    s = s.strip()
    bt = _bracket_town(s)
    if bt and bt[1]:
        return bt
    words = s.split()
    for k in (2, 1):
        if len(words) > k:
            cand = " ".join(words[-k:])
            cu = cand.upper().strip(".")
            if cu in known_towns and cu not in _BIZ_SKIP:
                return " ".join(words[:-k]).strip(), cand
    return s, ""


def parse_simple_party_itemwise(text):
    NUM = r'-?\d[\d,]*\.?\d*'
    c = re.sub(r'\s+', '', text.lower())
    lines = text.split('\n')

    # ---- Layout A: Orion "Product Party Analysis" (product is the heading, parties are the rows) ----
    if 'productpartyanalysis' in c and 'codepartynameareaqtyfreeamount' in c:
        headers = ["Party Name", "Area", "Product Name", "Qty", "Free", "Amount"]
        rows = []; product = None
        prod_re = re.compile(r'^Product\s*:\s*\S+\s+(.+)$', re.I)
        skip_re = re.compile(r'^\s*(Product Total|Total\s*:|CODE PARTY NAME|Powered By|.*FY\s*:|Product Party Analysis)', re.I)
        row3 = re.compile(r'^([A-Z0-9]{5})\s+(.+?)\s+(\d+)\s+(\d+)\s+(' + NUM + r')\s*$')
        row2 = re.compile(r'^([A-Z0-9]{5})\s+(.+?)\s+(\d+)\s+(' + NUM + r'\.\d{2})\s*$')
        rowq = re.compile(r'^([A-Z0-9]{5})\s+(.+?)\s+(\d+)\s*$')
        for ln in lines:
            s = ln.strip()
            if not s: continue
            pm = prod_re.match(s)
            if pm: product = pm.group(1).strip(); continue
            if skip_re.match(s): continue
            if product is None: continue
            m = row3.match(s)
            if m: rows.append([m.group(2), '', product, m.group(3), m.group(4), m.group(5)]); continue
            m = row2.match(s)
            if m: rows.append([m.group(2), '', product, m.group(3), '', m.group(4)]); continue
            m = rowq.match(s)
            if m: rows.append([m.group(2), '', product, m.group(3), '', '']); continue
        return headers, rows

    # ---- Layout B: "Company - Customer - Item wise Sale" (CUSTOMER: heading, item rows) ----
    if 'company-customer-itemwisesale' in c or ('customer-itemwisesale' in c and 'itemnamepackqty' in c):
        headers = ["Product Name", "Pack", "Qty", "Free", "Amount", "Party Name", "Area"]
        rows = []; party = ''; party_area = ''
        cust_re = re.compile(r'^CUSTOMER\s*:\s*(.+)$', re.I)
        skip_re = re.compile(r'^\s*(TOTAL\s*:|GRAND TOTAL|ITEM NAME|FROM\s*:|COMPANY|\[ KLM|Cont\.\.\.\.|Page\s*:)', re.I)
        # qty/free/amount each may be '-' or a decimal (e.g. 5.50 0.50)
        row = re.compile(r'^(.*?\S)\s+(-|' + NUM + r')\s+(-|' + NUM + r')\s+(-|' + NUM + r')\s*$')
        # Pre-scan: collect the towns that appear inside brackets on CUSTOMER
        # headings so a bare trailing town (no brackets) is only promoted when the
        # same document parenthesises it elsewhere -> never invents a town.
        known_towns = set()
        for ln in lines:
            cm = cust_re.match(ln.strip())
            if not cm:
                continue
            bt = _bracket_town(cm.group(1).strip())
            if bt and bt[1]:
                known_towns.add(bt[1].upper().strip("."))
        for ln in lines:
            s = ln.strip()
            if not s: continue
            cm = cust_re.match(s)
            if cm:
                party, party_area = _split_b_party(cm.group(1).strip(), known_towns)
                continue
            if skip_re.match(s): continue
            if not party: continue
            m = row.match(s)
            if m: rows.append([m.group(1), '', m.group(2), m.group(3), m.group(4), party, party_area])
        return headers, rows

    # ---- Layout D/E: "Customer-Product wise Sales" (SwilERP); CODE-NAME party heading, product rows ----
    if 'customer-productwisesales' in c and 'productcodeproductnamepacking' in c:
        headers = ["Product Code", "Product Name", "Pack", "Qty", "Free", "Amount", "Party Name", "Area"]
        rows = []; party = None; party_area = ''
        skip_re = re.compile(r'^\s*(-{3,}|\*+|Page No\.|TOTAL\b|GRAND TOTAL|Product Code\s|.*Customer-Product wise|Powered By|\.\.\.Continued|FY\s*:)', re.I)
        trail3 = re.compile(r'^(\S+)\s+(.*?\S)\s+(' + NUM + r')\s+(' + NUM + r')\s+(' + NUM + r')\s*$')
        trail2 = re.compile(r'^(\S+)\s+(.*?\S)\s+(' + NUM + r')\s+(' + NUM + r')\s*$')
        # FIX (SATYAM): allow ',' in the CODE segment (and widen 10->12) so
        # headings like "AM..,-ABHISHEK MEDICAL,..." / "MC,.-MAYALOK MEDICAL,..." /
        # "SB,,-SHREE BALAJEE MEDIMART,..." are recognised as party headings
        # instead of being swallowed into the previous party's rows. The trailing
        # numeric-value guard still keeps product rows out.
        party_re = re.compile(r'^[A-Za-z0-9.,/]{2,12}-.+')
        for ln in lines:
            s = ln.strip()
            if not s: continue
            if skip_re.match(s): continue
            if party is not None:
                m = trail3.match(s)
                if m:
                    rows.append([m.group(1), m.group(2), '', m.group(3), m.group(4), m.group(5), party, party_area]); continue
                m = trail2.match(s)
                if m:
                    rows.append([m.group(1), m.group(2), '', m.group(3), '', m.group(4), party, party_area]); continue
            # party heading: short code, hyphen, then name; must not end in a numeric value column.
            # The town is folded into the heading as "...,<TOWN>[,(phone)]" -> split it out to Area.
            if party_re.match(s) and not re.search(r'\d\s*$', s):
                party, party_area = _split_dp_party(s); continue
            if party_re.match(s) and ('(' in s or ',' in s):
                party, party_area = _split_dp_party(s); continue
        return headers, rows

    return [], []