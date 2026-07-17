import re


# Party-band phone marker. Orion glues star-noise into the token on some rows
# (e.g. "P*h*:*" / "STORES(E)P*h*:*"), so match "Ph" allowing interspersed '*'
# and a following ':' that may also carry a '*'. The marker splits <NAME> from
# the trailing <phone(s)> <TOWN> tail.
_PH_MARK = re.compile(r'\*?P\*?h\*?\s*:\*?', re.I)


def _split_party(rest):
    """Split the text after 'PARTY :' into (party_name, party_location).

    Bands look like:
        "AMBAJI MEDICAL&GEN STORE(AVINA)**** Ph: - 7798049276 AMBERNATH"
        "ARYA CHEMIST Ph: - AMBERNATH WEST"            (no phone)
        "DARSHAN MEDICAL STORE**** Ph:8390439272 - AMBERNATH"
        "MATAJI ... Ph:7263941527 - 9867290317 AMBERNATH"  (two phones)
        "TIRATH MEDICO**** Ph:8087890785. - 8087890785BADLAPUR"  (phone glued to town)

    NAME = everything before the 'Ph' marker (trailing '*' decoration stripped).
    TOWN = the trailing alphabetic run of the phone tail: drop the leading
    hyphen/phone/PIN tokens, then the town is what remains from the first letter
    on (a phone digit-run glued to the town is peeled)."""
    s = rest.strip()
    m = _PH_MARK.search(s)
    if m:
        name = s[:m.start()].strip()
        tail = s[m.end():].strip()
    else:
        # No 'Ph' marker at all -> the whole thing is the name; no reliable town.
        name = s
        tail = ""
    # Clean trailing star/space decoration off the name.
    name = re.sub(r'[\*\s]+$', '', name).strip()

    town = ""
    if tail:
        # The town is the last alphabetic-leading segment. Walk the tokens and
        # keep the tail once we hit a token that STARTS with a letter (a real
        # town word), peeling a leading phone digit-run glued to it.
        # First, collapse the leading "- <phone> [- <phone>]" clutter: split on
        # whitespace and find the first token that contains a letter.
        toks = tail.split()
        start = None
        for i, tk in enumerate(toks):
            # strip a leading glued phone digit-run + separators
            core = re.sub(r'^[\d\-\.\*/,]+', '', tk)
            if re.search(r'[A-Za-z]', core):
                start = i
                # rebuild this token without the glued phone prefix
                toks = toks[:i] + [core] + toks[i + 1:]
                break
        if start is not None:
            town = " ".join(toks[start:]).strip()
            # Drop a trailing PIN code / stray punctuation but keep bracket towns
            # like "AMBERNATH (EAST)".
            town = re.sub(r'\s*\d{3}\s*\d{3}\.?\s*$', '', town).strip()
            town = town.strip(' .,-')
    return name, town


def parse_party_product_analysis_orion(text):
    """METRO MEDICAL AGENCIES "Party Product Analysis" (Orion Computer Services).

    PARTY bands -> product detail rows. Column header:
        CODE PRODUCT NAME PACK QTY FREE REPL VALUE
    Detail row = <CODE> <PRODUCT NAME (pack tail may stay)> <PACK> <QTY> <FREE>
    <REPL> <VALUE>, ending in three integers then a 2-dp value. QTY/FREE/VALUE
    map to canonicals; REPL (a replacement-qty column) is carried raw so it is
    never forced into a canonical. Qty is read from its own column and NEVER
    derived from VALUE.

    Returns (headers, rows) like the other party_pdf text parsers."""
    headers = [
        "Party Name", "Party Location", "Code", "Product Name",
        "Pack", "Qty", "Free", "Repl Qty", "Amount",
    ]

    c = re.sub(r'\s+', '', text.lower())
    # Detect-gate guard (matches the registry gate). Harmless no-op if a caller
    # ever hands this parser a file it does not own.
    if not ("partyproductanalysis" in c
            and "codeproductnamepackqtyfreereplvalue" in c):
        return [], []

    NUM = r'-?\d[\d,]*'
    # Detail row: 5-char alnum code -> middle (product name + pack) -> QTY FREE
    # REPL (ints) -> VALUE (2dp). The middle is non-greedy so the four trailing
    # numbers anchor the split; VALUE is always decimal in this ERP. QTY/FREE/
    # REPL/VALUE may be NEGATIVE (sales-return lines, e.g. "-2 0 0 -1098.30"),
    # which the PARTY TOTAL subtotals include — so a leading '-' is allowed.
    row_re = re.compile(
        r'^([A-Za-z0-9]{4,6})\s+(.+?)\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)\s+(' + NUM + r'\.\d{2})\s*$'
    )
    party_re = re.compile(r'^\s*PARTY\s*:\s*(.+)$', re.I)
    # Skip band totals, grand total and the Orion page footer/header echoes.
    skip_re = re.compile(
        r'^\s*(PARTY\s+TOTAL\b|GRAND\s+TOTAL\b|CODE\s+PRODUCT\s+NAME'
        r'|Powered\s+By\b|Party\s+Product\s+Analysis\b|FY\s*:'
        r'|METRO\s+MEDICAL\s+AGENCIES\b)',
        re.I,
    )

    rows = []
    party_name = ""
    party_loc = ""
    for ln in text.split('\n'):
        s = ln.strip()
        if not s:
            continue
        pm = party_re.match(s)
        if pm:
            party_name, party_loc = _split_party(pm.group(1))
            continue
        if skip_re.match(s):
            continue
        if not party_name:
            continue
        m = row_re.match(s)
        if not m:
            continue
        code = m.group(1)
        middle = m.group(2).strip()
        qty = m.group(3)
        free = m.group(4)
        repl = m.group(5)
        value = m.group(6)
        # PACK: best-effort peel of a trailing pack token off the middle text
        # (e.g. "... 20GM", "... 100 GM", "... 10S", "... 15 GRM", "... 150 ML").
        # The product name keeps its pack tail per spec; PACK is a convenience
        # column, so only split when a clear pack token is present.
        product_name = middle
        pack = ""
        pm2 = re.search(
            r'\s(\d+\s*(?:GM|GRM|ML|MG|G|S|N|TAB|CAP|KG|LTR|L|DT|GML)\b\.?'
            r'|\d+\s?[A-Z]{1,4})\s*$',
            middle, re.I,
        )
        if pm2:
            pack = pm2.group(1).strip()
        rows.append([
            party_name, party_loc, code, product_name,
            pack, qty, free, repl, value,
        ])
    return headers, rows
