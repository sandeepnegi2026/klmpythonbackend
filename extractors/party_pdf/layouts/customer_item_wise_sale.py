import io
import re

# ---------------------------------------------------------------------------
# RAKESH MEDICAL STORES AGENCIES (Shimla) — LOGIC ERP
# "CUSTOMER+ITEM WISE SALE" report (one file per KLM division / period).
#
# Report furniture (portrait):
#   RAKESH MEDICAL STORES AGENCIES(SHIMLA)
#   CUSTOMER+ITEM WISE SALE FROM dd/mm/yyyy TO dd/mm/yyyy
#   Page No.: N of M ...
#   -- 3-line column header --
#     SN | SALE | FREE | TOTAL | GROSS      (row 1, right side)
#     CUSTOMER NAME | ITEM NAME             (row 2, left side)
#     O. | QTY | QTY | QTY | AMOUNT         (row 3, right side)
#   ...data...
#   <printed grand total>  SALE  FREE  TOTAL  GROSS   (last line, no SN, no alpha)
#
# BODY = per-customer groups. Each group is one or more item detail rows
# (SN + CUSTOMER NAME + ITEM NAME + the 4 numeric columns) followed by a
# numbers-only sub-total line (NO SN, no alpha) that repeats the group's
# SALE / FREE / TOTAL / GROSS aggregate. The final numbers-only line is the
# printed grand total.
#
# TWO PHYSICAL DIALECTS across the reference files:
#   * "MAY PDF PART.pdf"  — clean flat text: customer and item are separated by
#     " - " and the item starts with "KLM"; the SN + numbers print on their own
#     visual line just under the customer/item text line. Per-item numbers are
#     clean and reconcile individually.
#   * "klm party wise....pdf" — the CUSTOMER NAME and ITEM NAME glyph runs are
#     laid down as two SEPARATE left-to-right text runs on the SAME baseline in
#     the SAME x-region, so pdfplumber's default (x-sorted) line text interleaves
#     them character-by-character ("ALL WELL CHEMISTSK LKMU SNUIOMSPATLI..." for
#     customer "ALL WELL CHEMISTS" + item "KLM SUNIT COMP..."). Pack digits inside
#     the ITEM NAME also leak into the SALE/FREE/TOTAL x-bands, so per-item numbers
#     are unreliable. The numbers-only sub-total lines, however, are always clean.
#
# STRATEGY (uniform, reconciles on both dialects):
#   Parse positionally with pdfplumber. Anchor the 4 numeric columns on the header
#   words SALE/FREE/TOTAL/GROSS (x differs per file).
#
#   For the interleaved dialect the two text streams cannot be separated by an
#   x-sort (their character x-ranges overlap), but they de-interleave cleanly in
#   DRAWING order: within each visual line pdfplumber's char stream lays down
#   SN + CUSTOMER NAME first (x column ~98), then the ITEM NAME run (x resets back
#   to the item column ~214), then the numeric columns (x resets into the number
#   band). We therefore walk the char stream in drawing order and split it into
#   customer / item / numeric segments by detecting the backward x0 resets; the
#   numeric band is positionally fixed so its chars are peeled regardless of run.
#   A KLM-only continuation line (item under the same customer) simply has its
#   first text char already in the item column -> no customer, item only.
#
#   Groups: each customer's item detail line(s) are followed by a numbers-only
#   sub-total line carrying the group's clean SALE/FREE/TOTAL/GROSS aggregate. We
#   emit ONE row per customer using the sub-total's clean numbers:
#       qty       <- SALE  QTY
#       free_qty  <- FREE  QTY
#       amount    <- GROSS AMOUNT   (TOTAL QTY = SALE + FREE, kept as raw)
#   party_name  = the group's de-interleaved CUSTOMER NAME.
#   product_name = the group's de-interleaved ITEM NAME run(s), joined with ' | '.
#   The trailing grand-total line (numbers-only, but the LAST such line and not
#   preceded by group text) is skipped.
#
#   The clean " - "/KLM dialect ("MAY PDF PART.pdf") has NO interleaving: its
#   customer starts in the customer column and its item run starts at ~214 just the
#   same, so the same drawing-order splitter recovers both without special-casing.
#
# Reconciles EXACTLY on both reference files: summed qty / free_qty / amount
# equal the printed "Grand Total  SALE  FREE  TOTAL  GROSS".
#   klm party wise....pdf : 129.58 / 12.42 / 25027.58  (TOTAL 142)
#   MAY PDF PART.pdf      : 368.50 / 71.50 / 108572.78 (TOTAL 440)
# ---------------------------------------------------------------------------

H = ['Party Name', 'Product Name', 'Qty', 'Free', 'Total Qty', 'Amount']

# allow leading-dot decimals like ".42" (the vendor prints fractional free qty
# without a leading zero) as well as ordinary "1,234.56" / "-5" / "9".
_NUM = re.compile(r'^-?(?:[\d,]+(?:\.\d+)?|\.\d+)$')

# The LOGIC ERP "CUSTOMER+ITEM WISE SALE" column geometry differs per file, so the
# row splitter derives its boundaries from the header word x0 (see _find_anchors)
# rather than hard-coding them. Only this small backward-jump threshold is fixed.
_RESET = 8.0                # backward x0 jump (pt) that marks a new drawing run


def _num(t):
    try:
        return float(t.replace(',', ''))
    except (ValueError, AttributeError):
        return 0.0


def _lines_by_top(words):
    lines = {}
    for w in words:
        lines.setdefault(round(w['top'], 1), []).append(w)
    return lines


def _find_anchors(pages):
    """Return {'SALE','FREE','TOTAL','GROSS': x1} from the header row that
    carries SALE FREE TOTAL GROSS (right-side header line). Also carries the
    left-edge x0 of the SALE / CUSTOMER / ITEM header words (keys 'SALE_X0',
    'CUSTOMER_X0', 'ITEM_X0') so the row splitter can derive its column
    boundaries per-file instead of hard-coding them."""
    all_words = []
    for pg in pages:
        all_words.extend(pg.extract_words())
    # CUSTOMER / ITEM header words may sit on a different y than SALE (multi-row
    # header in the klm dialect), so scan them across ALL header words.
    cust_x0 = item_x0 = None
    for w in all_words:
        if w['text'] == 'CUSTOMER' and cust_x0 is None:
            cust_x0 = w['x0']
        elif w['text'] == 'ITEM' and item_x0 is None:
            item_x0 = w['x0']
    for pg in pages:
        for y, ws in _lines_by_top(pg.extract_words()).items():
            txt = ' '.join(w['text'] for w in ws)
            if 'SALE' in txt and 'FREE' in txt and 'TOTAL' in txt and 'GROSS' in txt:
                anc = {}
                for w in ws:
                    if w['text'] in ('SALE', 'FREE', 'TOTAL', 'GROSS'):
                        anc[w['text']] = w['x1']
                    if w['text'] == 'SALE':
                        anc['SALE_X0'] = w['x0']
                if len([k for k in anc if k in ('SALE', 'FREE', 'TOTAL', 'GROSS')]) == 4:
                    if cust_x0 is not None:
                        anc['CUSTOMER_X0'] = cust_x0
                    if item_x0 is not None:
                        anc['ITEM_X0'] = item_x0
                    return anc
    return None


def _text(chars):
    return ''.join(c['text'] for c in chars).strip()


def _clean_product(text):
    """Tidy a de-interleaved ITEM NAME: collapse whitespace and drop any dangling
    number fragment the SALE column can leak onto the right edge of the run (e.g.
    the leading '4.' of a fractional SALE qty 4.58). A trailing standalone numeric
    token that is NOT preceded by a unit word is a leak, not part of the pack, so
    it is removed; genuine pack sizes ('50 GM', '150 ML') always end in letters."""
    text = re.sub(r'\s{2,}', ' ', text).strip()
    # a trailing run of digits/./, with no letters after it and following a space
    # is a numeric leak from the SALE column boundary -> strip it.
    text = re.sub(r'\s+[\d][\d,\.]*$', '', text).strip()
    return text


def _deinterleave_line(chars, geom):
    """Split ONE visual data line (chars in DRAWING order) into
    (sn, customer_text, item_text).

    geom carries the per-file boundaries (sale_x, cust_start, item_lo, item_hi).
    The SN prints far left (x1 <= cust_start); the CUSTOMER NAME run prints next;
    the ITEM NAME run always begins with 'KLM'. Two dialects, one walk:
      * clean dialect (forward flow, ' - ' before the item): the customer and
        item never overlap in x, so the item simply starts at the 'KLM' token.
      * interleaved dialect (klm party wise..): the item 'KLM' run starts at a
        backward x0 reset back into the item column, before the header ITEM word.
    We therefore switch customer -> item when we see the 'KLM' trigram OR a
    backward reset landing in the item column. A KLM-only continuation line has
    its first text char already at/after the item column, so it has no customer.
    Chars in the numeric band (x0 >= num_left) are numbers, dropped from text."""
    num_left = geom['num_left']
    cust_start = geom['cust_start']
    item_lo = geom['item_lo']
    item_hi = geom['item_hi']
    sn_c, cust_c, item_c = [], [], []
    seg = 'cust'
    prev = None
    started_text = False
    n = len(chars)
    for i, c in enumerate(chars):
        x0 = c['x0']
        if x0 >= num_left:               # numeric band -> not text
            prev = x0
            continue
        if not started_text and c['x1'] <= cust_start:
            sn_c.append(c)               # leading SN
            prev = x0
            continue
        # 'KLM' trigram starting here (item name always begins KLM)
        klm = (
            c['text'] == 'K'
            and i + 2 < n and chars[i + 1]['text'] == 'L'
            and chars[i + 2]['text'] == 'M'
            and x0 >= item_lo - 4.0
        )
        if not started_text:
            started_text = True
            seg = 'item' if (x0 >= item_lo or klm) else 'cust'
        elif seg == 'cust' and (
            klm
            or (prev is not None and x0 < prev - _RESET
                and item_lo <= x0 <= item_hi)
        ):
            seg = 'item'                 # customer run ends, item run begins
        (cust_c if seg == 'cust' else item_c).append(c)
        prev = x0
    return _text(sn_c), _text(cust_c), _text(item_c)


def parse_customer_item_wise_sale(text, file_bytes=None):
    if not file_bytes:
        return H, []

    import pdfplumber

    rows = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        if not pdf.pages:
            return H, []

        anc = _find_anchors(pdf.pages)
        if not anc:
            return H, []

        # numeric column centres, right-anchored on the header word x1
        cols = [('sale', anc['SALE']), ('free', anc['FREE']),
                ('total', anc['TOTAL']), ('gross', anc['GROSS'])]
        sale_x = anc['SALE']            # SALE header x1 (right edge of the column)

        # per-file text-column boundaries, derived from the header word x0.
        # cust_start: SN | CUSTOMER divider (a few pt left of CUSTOMER NAME).
        # item_lo/item_hi: the x window where the ITEM NAME run may begin. The
        # klm-dialect item run starts a little LEFT of the ITEM header word, so
        # widen the window generously on the low side but keep it left of SALE.
        # num_left: chars at/after this x are in the numeric band (text is peeled
        # here). The SALE VALUES are right-aligned to the SALE header x1; pack text
        # ('50 GM') sits just left of them, so a cut a few pt inside the SALE header
        # word right edge keeps the pack while dropping the right-aligned value.
        cust_x0 = anc.get('CUSTOMER_X0', 96.0)
        item_x0 = anc.get('ITEM_X0', 236.0)
        geom = {
            'sale_x': sale_x,
            'num_left': sale_x - 8.0,
            'cust_start': cust_x0 - 5.0,
            'item_lo': item_x0 - 28.0,
            'item_hi': item_x0 + 20.0,
        }

        def bucket(x1):
            best, bd = None, 1e9
            for name, ax in cols:
                d = abs(x1 - ax)
                if d < bd:
                    bd, best = d, name
            # values are right-aligned near/just past their header word; a wide
            # tolerance is safe because these are the ONLY numbers on a
            # sub-total line (no pack/item digits to steal a column). Longer
            # GROSS amounts extend well right of the header word, so keep it wide.
            return best if bd < 55 else None

        def subtotal_vals(line_chars):
            """Read the clean SALE/FREE/TOTAL/GROSS aggregate off a numbers-only
            line: tokenise the numeric-band chars by x-gap and bucket each to a
            column by its right edge."""
            nchars = sorted(
                (c for c in line_chars
                 if c['x0'] >= sale_x - 45.0 and c['text'].strip()),
                key=lambda c: c['x0'],
            )
            toks, cur = [], []
            for c in nchars:
                if cur and c['x0'] - cur[-1]['x1'] > 3.0:
                    toks.append(cur)
                    cur = []
                cur.append(c)
            if cur:
                toks.append(cur)
            vals = {'sale': 0.0, 'free': 0.0, 'total': 0.0, 'gross': 0.0}
            for tk in toks:
                s = ''.join(c['text'] for c in tk).strip()
                if not _NUM.match(s):
                    continue
                b = bucket(tk[-1]['x1'])
                if b:
                    vals[b] = _num(s)
            return vals

        pending_cust = None    # open group's customer (party_name)
        pending_items = []      # open group's item lines (product_name parts)

        for pg in pdf.pages:
            # group CHARS by baseline; keep DRAWING ORDER within each line.
            page_lines = {}
            for c in pg.chars:
                page_lines.setdefault(round(c['top'], 0), []).append(c)

            for y in sorted(page_lines):
                line = page_lines[y]
                sn, cust, item = _deinterleave_line(line, geom)

                # page furniture / header sub-lines -> skip
                low = (cust + ' ' + item).lower()
                if ('customer name' in low or 'item name' in low
                        or 'sale qty' in low
                        or low.startswith('page no')
                        or low.startswith('printed by')
                        or 'wise sale' in low
                        or 'medical stores agencies' in low
                        or low.startswith('o. qty')
                        or 'workstation' in low
                        or re.search(r'\bfrom\b.*\bto\b', low)):
                    continue

                has_text = bool(re.search('[A-Za-z]', cust + item))

                if not has_text:
                    # numbers-only line. Two kinds:
                    #   * item-detail number line (clean dialect, e.g. MAY) — carries
                    #     a leading SN in the SN column. It holds a SINGLE item's
                    #     numbers; do NOT close the group here (the group's clean
                    #     aggregate arrives on the SN-less sub-total line).
                    #   * sub-total line — NO SN; holds the group's clean aggregate.
                    if sn:
                        continue
                    vals = subtotal_vals(line)
                    if not (vals['total'] or vals['gross']):
                        continue
                    # grand total = trailing numbers-only line with no open group
                    if pending_cust is None and not pending_items:
                        continue
                    party = pending_cust or ''
                    product = ' | '.join(pending_items)
                    rows.append([
                        party, product,
                        "%g" % vals['sale'], "%g" % vals['free'],
                        "%g" % vals['total'], "%.2f" % vals['gross'],
                    ])
                    pending_cust = None
                    pending_items = []
                    continue

                # data line: a customer-bearing detail row (cust set) or a
                # KLM-only continuation row under the current customer (item only).
                if cust:
                    pending_cust = re.sub(r'\s{2,}', ' ', cust).strip()
                if item:
                    it = _clean_product(item)
                    if it:
                        pending_items.append(it)

    return H, rows
