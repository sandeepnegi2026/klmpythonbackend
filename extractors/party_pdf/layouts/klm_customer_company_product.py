import re

# KLM "Customer,Company And Product Sales" (SRI DURGA SRINIVASA PHARMA & VETS).
#
# Dashed-band party report. Structure:
#   SRI DURGA SRINIVASA PHARMA & VETS
#   Customer,Company And Product Sales
#   From 01/05/2026 To 27/05/2026        Page : 1
#   Company :KLM (<DIVISION>)
#   ----
#   Product Name Packing Qty Free Rate Amount      <- fixed column header (repeats/page)
#   ----
#   Customer :<NAME>  Add :<CITY>                  <- party band (area follows "Add :")
#   ----
#   <PRODUCT NAME ...> <PACKING> <Qty> <Free> <Rate> <Amount>   <- single-line rows
#   ...
#   Total: <amount>                                <- per-band footer
#   ----
#
# Rows are clean single lines (no wrap / no batch / no inv / no date). Each row's
# last 4 whitespace tokens are qty free rate amount (floats like "4.0 0.0 242.86
# 971.44"); the token immediately before them is the packing (30gm/10s/100ml/...),
# and everything before that is the product name.
#
# The parser is intentionally text-based (word x-position not needed: the vendor
# prints one product per line with no interior blank columns). Only emits rows
# while a "Customer :" band is active, so title/header/footer noise cannot leak in.
#
# A THIRD dialect (JAYASRI) prints two extra leading columns (FeedDate, FeedNO) and
# WRAPS each row across two physical lines (see _parse_wrapped) — gated separately
# on the "FeedNO" header token so the single-line variants stay byte-identical.

# line-A of the wrapped dialect: "<date> <feedno> <product...> <packing> <qty> <free>"
_WRAP_LINE_A = re.compile(r'^\d{1,2}/\d{1,2}/\d{4}\s+\S+\s+')
# line-B of the wrapped dialect: "<rate> <amount>" (exactly two numeric cells)
_WRAP_LINE_B = re.compile(r'^(-?\d[\d,]*\.?\d*)\s+(-?\d[\d,]*\.?\d*)\s*$')

# A value cell (qty/free/rate/amount) prints as a float WITH a decimal point
# ("20.0 0.0 138.98 2779.60"). Requiring the decimal is what lets the glyph-repair
# below fix a corrupted amount ("2779.F60") without ever swallowing a packing token
# like "60ML"/"10`S"/"30GM" (no decimal point -> never repaired).
_FLOAT_CELL = re.compile(r'^-?\d[\d,]*\.\d+$')


def _peel_numeric_run(toks, num_tok, repair=False):
    """Peel the trailing run of numeric cells off a row, returning (nvals, rest).

    With ``repair=False`` this is the plain peel (byte-identical to the original
    inline loop). With ``repair=True`` it tolerates ONE glyph-corrupted cell inside
    the value run — a PROFITMAKER watermark can inject a stray letter into an amount
    ("2779.F60" for 2779.60) or drop a bare letter token before it ("... 180.72 O
    361.44 237.19"), which otherwise halts the peel and silently drops an
    otherwise-clean row. The repaired value must be a FLOAT WITH A DECIMAL (so a
    packing token is never mistaken for a value), and only a single one-char alpha is
    tolerated. Called with repair=True ONLY as a fallback when the plain peel already
    failed to reach four value cells, so rows that parse today are never touched."""
    toks = list(toks)
    nvals = []
    used_repair = False
    while toks:
        t = toks[-1]
        if num_tok.match(t):
            nvals.insert(0, toks.pop())
            continue
        if repair and not used_repair:
            cleaned = t.replace('`', '')
            if len(re.findall(r'[A-Za-z]', cleaned)) == 1:
                fixed = re.sub(r'[A-Za-z]', '', cleaned)
                if _FLOAT_CELL.match(fixed):        # glyph inside a value, e.g. 2779.F60
                    nvals.insert(0, fixed)
                    toks.pop()
                    used_repair = True
                    continue
            if re.fullmatch(r'[A-Za-z]', t):        # stray bare letter between numerics
                toks.pop()
                used_repair = True
                continue
        break
    return nvals, toks


def _parse_wrapped(text, headers, band_re, num_tok):
    """JAYASRI dialect: FeedDate/FeedNO leading cols + each row wrapped over two
    lines (date feedno product pack qty free / rate amount). Party bands are the
    same "Customer :<name> Add :<area>". Qty/Free are the trailing two numerics of
    line-A (packing has a unit letter so it stops the peel); Rate/Amount are line-B.
    Amount == Qty*Rate on every reference row (2*678.58 = 1357.16)."""
    rows = []
    party = area = ""
    lines = [ln.strip() for ln in text.splitlines()]
    n = len(lines)
    i = 0
    while i < n:
        s = lines[i]
        if not s:
            i += 1
            continue
        m = band_re.match(s)
        if m:
            party = m.group('party').strip()
            area = m.group('area').strip()
            i += 1
            continue
        if party and _WRAP_LINE_A.match(s) and i + 1 < n:
            lb = _WRAP_LINE_B.match(lines[i + 1])
            if lb:
                rest = s.split()[2:]           # drop <date> <feedno>
                nvals = []                     # trailing qty, free
                while rest and num_tok.match(rest[-1]) and len(nvals) < 2:
                    nvals.insert(0, rest.pop())
                if len(nvals) == 2 and len(rest) >= 2:
                    packing = rest[-1]
                    product = " ".join(rest[:-1]).strip()
                    if product:
                        rows.append([party, area, product, packing,
                                     nvals[0], nvals[1], lb.group(1), lb.group(2)])
                    i += 2
                    continue
        i += 1
    return headers, rows


def parse_klm_customer_company_product(text, file_bytes=None):
    headers = ["Party Name", "Area", "Product Name", "Packing",
               "Qty", "Free", "Rate", "Amount"]
    rows = []

    # party band:  Customer :<name>  Add :<area>
    # area follows "Add :" (NOT a comma). The vendor may right-truncate the
    # customer name (e.g. "...STORES(PT") — keep it as printed.
    band_re = re.compile(r'^Customer\s*:\s*(?P<party>.+?)\s+Add\s*:\s*(?P<area>.*)$', re.I)

    # product row: <product> <packing> <qty> <free> <rate> <amount> [<mrp> ...]
    # The value run is FRONT-anchored: qty/free/rate/amount are the FIRST four
    # numeric cells, NOT the last four. A KLM variant (SRI BALAJI) prints a 6th
    # "MRP" column (header "...Rate Amount MRP"); back-anchoring the last 4 there
    # shifted every column right by one (amount silently read the MRP price). The
    # original SRI DURGA files print exactly 4 numerics, for which first-4==last-4,
    # so this is byte-identical for them and only corrects the 5-numeric variant.
    NUM_TOK = re.compile(r'^-?\d[\d,]*\.?\d*$')

    # WRAPPED (FeedDate/FeedNO) dialect — two leading cols + rows split over two
    # lines. Gated on the FeedNO header token so the single-line variants below are
    # never affected.
    if re.search(r'\bFeedNO\b', text, re.I):
        return _parse_wrapped(text, headers, band_re, NUM_TOK)

    # lines that are never product rows / never party bands
    skip_re = re.compile(
        r'^\s*('
        r'-{3,}'                              # dashed separators
        r'|Total\s*:'                         # per-band footer
        r'|Grand\s*Total'                     # (defensive) grand total
        r'|Page\s*:'                          # page markers
        r'|From\s+\d'                         # From <date> ... line
        r'|Company\s*:'                       # Company :KLM (...)
        r'|Customer\s*,\s*Company'            # title line
        r'|Product\s+Name\s+Packing'          # column header
        r')', re.I)

    party = ""
    area = ""
    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            continue

        m = band_re.match(s)
        if m:
            party = m.group('party').strip()
            area = m.group('area').strip()
            continue

        if skip_re.match(s):
            continue

        if not party:
            continue

        # peel the trailing run of pure-numeric cells off the row
        toks = s.split()
        # tolerate ONE glyph-corrupt trailing MRP cell (e.g. "1F68.75" for 168.75,
        # "2F05.00" for 205.00) which would otherwise halt the peel and drop the row;
        # MRP is unused, so discarding a mangled trailing non-numeric-with-digit is safe.
        if toks and not NUM_TOK.match(toks[-1]) and re.search(r'\d', toks[-1]):
            toks = toks[:-1]
        nvals, rest = _peel_numeric_run(toks, NUM_TOK, repair=False)
        if len(nvals) < 4:
            # The plain peel dropped this row. A PROFITMAKER glyph watermark may have
            # injected a stray letter INTO the value run (amount "2779.F60", or a bare
            # "O" before an amount — SRI BALAJI DERMA-D1: NEVLON CALOE LOTION, ONITRAZ
            # SB 130). Retry with a single one-shot repair and ADOPT it only if it now
            # yields the full >=4 value cells + product/packing, so this branch can only
            # RECOVER a currently-dropped row, never alter one that already parses.
            r_nvals, r_rest = _peel_numeric_run(toks, NUM_TOK, repair=True)
            if len(r_nvals) >= 4 and len(r_rest) >= 2:
                nvals, rest = r_nvals, r_rest
        # need qty/free/rate/amount (>=4 numeric cells) and product+packing before them
        if len(nvals) < 4 or len(rest) < 2:
            continue
        packing = rest[-1]
        product = " ".join(rest[:-1]).strip()
        if not product:
            continue

        # FRONT four numerics are qty/free/rate/amount; any 5th+ (MRP) is ignored
        qty, free, rate, amt = nvals[0], nvals[1], nvals[2], nvals[3]
        rows.append([party, area, product, packing, qty, free, rate, amt])

    return headers, rows
