import io
import re

# ---------------------------------------------------------------------------
# VASAN MEDICAL AGENCIES (Karur) "Areawise Sales Report" — KLM sub-stockist,
# legacy DOS-style monospace ERP export (one file per KLM division:
# COSMO / COSMOQ / COSMOCOR / DERMA / DERMACOR / PEDIA / PHARMA).
#
# Sibling of areawise_sales_billwise.py (JEYANTHI PHARMAA) — SAME ERP "Areawise
# Sales Report" title/furniture and SAME positional Courier-only + page-0-only
# techniques, but a DIFFERENT column ORDER: this export is PRODUCT-FIRST with the
# customer/area carried in a BAND (JEYANTHI has the customer as a COLUMN), so its
# header gate does not fire.
#
# Report furniture (landscape 842x595, Courier New 7.84pt):
#   VASAN MEDICAL AGENCIES / <address> / "Areawise Sales Report" /
#   "From 01/06/26 To 30/06/26 for COSMO KLM LABORATORIES PVT LTD" / dashed rule /
#   header "Product Name  Packi  Bill Number  Bill Date  Qty  Free  Repl  Sale Val"
#   / a 2nd dashed rule / then data.
#
# Body structure = AREA/CUSTOMER band -> item rows:
#   * a BAND line has no bill-date token. It is split POSITIONALLY by word x0:
#       x0 <  87           -> AREA   (e.g. "GANDHIGRAMAM", "KARUR EAST", "VELUR")
#       87 <= x0 < 240     -> CUSTOMER name
#       x0 >= 240          -> TOWN / place
#     The AREA prints only on the first customer band of the area; continuation
#     customer bands start at x0 ~= 87 (no area prefix) and inherit the carried
#     area. Reset the customer on "Customer Sub Total".
#   * an ITEM row carries a dd/mm/yy in the "Bill Date" x-band. Product name (incl.
#     its glued pack, e.g. "EKRAN AQUA GEL 50GM") is x0 < ~135; bill number
#     x0 163..216; the four trailing numerics are bucketed by right-edge x1:
#       x1 <= 325          -> Qty
#       325 < x1 <= 355    -> Free
#       355 < x1 <= 378    -> Repl  (always '-' in these 7; dropped)
#       x1 >  378          -> Sale Val (amount)
#     '-' -> 0.
#   * footer roll-ups "Customer Sub Total", "Area Total", "Grand Total" skipped.
#
# QUIRK: every page's content stream replicates the ENTIRE report (page-1 Grand
# Total already equals the full total; multi-page files draw the copies off-page
# at negative tops). Parse ONLY pdf.pages[0] to avoid tripled rows.
#
# Reconciles EXACTLY on all 7 reference files: summed Qty and summed Free equal
# the printed "Grand Total <Qty> <Free> - <Sale Val>" line and summed amount
# matches the printed Sale Val total.
# ---------------------------------------------------------------------------

H = ['Party Name', 'Area', 'Product Name', 'Pack', 'Bill No', 'Bill Date',
     'Qty', 'Free', 'Amount']

_DATE = re.compile(r'^\d{2}/\d{2}/\d{2}$')
_NUM = re.compile(r'^-?[\d,]+(?:\.\d+)?$')

# band-split x0 thresholds (see module note). Area tokens print at x0 9.4..70,
# customer starts at x0 ~86.4, town at x0 ~240 -> split at 80 and 235.
_AREA_MAX_X0 = 80.0
_TOWN_MIN_X0 = 235.0


def _num(t):
    if t == '-':
        return 0.0
    try:
        return float(t.replace(',', ''))
    except (ValueError, AttributeError):
        return 0.0


def _build_tokens(chars):
    """Group left-to-right chars of one visual line into (text, x0, x1) tokens.

    A token break is a literal space char OR a horizontal gap > 2pt (the
    monospace grid occasionally drops the space glyph between adjacent columns).
    """
    chars = sorted(chars, key=lambda c: c['x0'])
    toks = []
    cur = None
    for c in chars:
        if c['text'] == ' ':
            if cur is not None:
                toks.append(cur)
                cur = None
            continue
        if cur is None:
            cur = [c['text'], c['x0'], c['x1']]
        elif c['x0'] - cur[2] > 2.0:
            toks.append(cur)
            cur = [c['text'], c['x0'], c['x1']]
        else:
            cur[0] += c['text']
            cur[2] = c['x1']
    if cur is not None:
        toks.append(cur)
    return toks


def parse_vasan_areawise_billwise(text, file_bytes=None):
    if not file_bytes:
        return H, []

    import pdfplumber

    rows = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        if not pdf.pages:
            return H, []
        page = pdf.pages[0]  # page 1 holds the WHOLE report (see module note)

        # keep only Courier chars -> drops the Helvetica footer glyph-interleave
        chars = [c for c in page.chars if 'Courier' in c.get('fontname', '')]
        lines = {}
        for c in chars:
            lines.setdefault(round(c['top'], 1), []).append(c)

        started = False        # flipped on once the 2nd dashed rule is passed
        dash_count = 0
        area = ''
        customer = ''

        for y in sorted(lines):
            toks = _build_tokens(lines[y])
            if not toks:
                continue
            joined = " ".join(t[0] for t in toks).strip()
            if not joined:
                continue

            # dashed rule -> the 2nd one starts the data region
            if set(joined) <= set('- '):
                dash_count += 1
                if dash_count >= 2:
                    started = True
                continue
            if not started:
                continue

            # roll-up / total lines
            if joined.startswith('Grand Total'):
                continue
            if 'Customer Sub Total' in joined:
                customer = ''
                continue
            if joined.startswith('Area Total'):
                continue
            if joined.startswith('End Of Report'):
                continue

            # a bill-date token in the "Bill Date" x-band identifies an item row
            date_tok = None
            for t in toks:
                if 240 <= t[1] < 300 and _DATE.match(t[0]):
                    date_tok = t[0]
                    break

            if date_tok is None:
                # ---- BAND line: split positionally by word x0 -------------
                new_area = " ".join(t[0] for t in toks if t[1] < _AREA_MAX_X0).strip()
                cust = " ".join(
                    t[0] for t in toks
                    if _AREA_MAX_X0 <= t[1] < _TOWN_MIN_X0 and not _DATE.match(t[0])
                ).strip()
                if new_area:
                    area = new_area
                if cust:
                    customer = cust
                continue

            # ---- ITEM ROW (positional token bucketing) --------------------
            prod = " ".join(
                t[0] for t in toks if t[1] < 135 and not _DATE.match(t[0])
            ).strip()
            billno = ''
            for t in toks:
                if 160 <= t[1] < 220:
                    billno = t[0]
                    break

            qty = free = amount = 0.0
            for t in toks:
                if not _NUM.match(t[0]) and t[0] != '-':
                    continue
                if _DATE.match(t[0]):
                    continue
                x1 = t[2]
                if t[1] >= 300 and x1 <= 325:
                    qty = _num(t[0])            # Qty band
                elif 325 < x1 <= 355:
                    free = _num(t[0])           # Free band
                elif 355 < x1 <= 378:
                    pass                        # Repl band (always '-')
                elif x1 > 378:
                    amount = _num(t[0])         # Sale Val

            rows.append([
                customer, area, prod, '', billno, date_tok,
                "%g" % qty, "%g" % free, "%.2f" % amount,
            ])

    return H, rows
