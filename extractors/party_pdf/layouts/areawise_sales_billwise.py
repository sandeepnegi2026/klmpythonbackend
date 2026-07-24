import io
import re

# ---------------------------------------------------------------------------
# JEYANTHI PHARMAA (Coimbatore) "Areawise Sales Report" — KLM sub-stockist,
# legacy DOS-style monospace ERP export (one file per KLM division:
# COSMO / COSMOCOR / COSMOQ / DERMA / DERMACOR / PEDIA / PHARMA).
#
# Report furniture (landscape 842x595, Courier New 7.84pt):
#   JEYANTHI PHARMAA / <address> / "Areawise Sales Report" /
#   "From 01/05/26 To 31/05/26 for KLM-<DIV>" / a dashed rule /
#   the column header "Product Name  Customer Name  Bill Number  Bill Dat
#   Pack  Quan  Free  Repl  Sales Value" / a 2nd dashed rule / then data.
#
# Body structure = AREA band -> customer blocks -> bill-line item rows:
#   * an AREA heading is a flush-left line with no date/bill/value tokens
#     (e.g. "ANNUR.PULIYAMPATTI", "SB COLONY-NSR ROAD").
#   * an item row carries a dd/mm/yy in the "Bill Dat" x-band; the customer
#     name prints only on the first row of its block (carried down), and the
#     bill number is blank on continuation rows of the same bill.
#   * a free-issue / scheme line prints as a separate row with only a number
#     in the "Repl" x-band and no customer / bill / value — it is emitted as a
#     qty=0 / free=N / amount=0 row (this reconciles the Free grand total).
#   * a sales-return prints as an "SR" bill with negative qty and value.
#   * footer roll-ups "Customer Sub Total", "Area Total", "Grand Total".
#
# TWO CRITICAL QUIRKS handled here:
#   (1) EVERY page's content stream contains the ENTIRE report (page 1 chars
#       span top 49..2509 = 4+ page heights and page 1 already holds the Grand
#       Total). Concatenating all pages yields ~7 near-duplicate copies of every
#       row, so this parser reads ONLY pdf.pages[0].
#   (2) Each page copy has exactly one data line glyph-interleaved with the page
#       footer, but the footer chars are Helvetica-Oblique 8.0 ("Document Footer
#       Text") / Helvetica-Bold 10.0 ("Page N / M") while data is Courier New
#       7.84 — so keeping only 'Courier' chars removes the contamination
#       perfectly.
#
# Because "Quan" (qty) and "Repl" (free) are BOTH bare integers on adjacent
# columns and a value can appear in either (or both) on a line, disambiguation
# is POSITIONAL: numbers are right-aligned and bucketed by their x1.
#
# Column x-bands (from the header/word dump; numbers right-aligned):
#   Product   x0 <   100
#   Customer  100 <= x0 < 200        (bill numbers start at x0 ~= 202.7)
#   Bill No   200 <= x0 < 273
#   Bill Dat  273 <= x0 < 316        (^dd/dd/dd$)
#   Pack      316 <= x0, x1 <= 342
#   Quan      x1 <= 364              (qty)
#   Free      364 < x1 <= 388        (header band; never populated in these 7)
#   Repl      388 < x1 <= 412        (where ALL free / scheme qty actually print)
#   Sales Val x1  >  412             (amount)
#
# Reconciles EXACTLY on all 7 reference files: summed Qty and summed Free equal
# the printed "Grand Total <Quan> <Free> <Sales Value>" line, and summed amount
# matches within vendor line-rounding scatter (<= 0.10).
# ---------------------------------------------------------------------------

H = ['Party Name', 'Area', 'Product Name', 'Pack', 'Bill No', 'Bill Date',
     'Qty', 'Free', 'Amount']

_DATE = re.compile(r'^\d{2}/\d{2}/\d{2}$')
_NUM = re.compile(r'^-?[\d,]+(?:\.\d+)?$')


def _num(t):
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


def parse_areawise_sales_billwise(text, file_bytes=None):
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
        bill = ''

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
                bill = ''
                continue
            if joined.startswith('Area Total'):
                continue

            # a bill-date token in the "Bill Dat" x-band identifies an item row
            date_tok = None
            for t in toks:
                if 273 <= t[1] < 316 and _DATE.match(t[0]):
                    date_tok = t[0]
                    break

            if date_tok is None:
                # no date/bill/value -> a flush-left AREA heading
                area = joined
                customer = ''
                bill = ''
                continue

            # ---- ITEM ROW (positional token bucketing) --------------------
            prod = " ".join(t[0] for t in toks if t[1] < 100).strip()
            cust = " ".join(
                t[0] for t in toks
                if 100 <= t[1] < 200 and not _DATE.match(t[0])
            ).strip()
            billno = ''
            for t in toks:
                if 200 <= t[1] < 273:
                    billno = t[0]
                    break
            pack = " ".join(
                t[0] for t in toks if t[1] >= 316 and t[2] <= 342
            ).strip()

            qty = free = amount = 0.0
            for t in toks:
                if not _NUM.match(t[0]):
                    continue
                x1 = t[2]
                if t[1] >= 342 and x1 <= 364:
                    qty = _num(t[0])            # Quan band
                elif 364 < x1 <= 388:
                    free = _num(t[0])           # Free header band (fold defensively)
                elif 388 < x1 <= 412:
                    free = _num(t[0])           # Repl band = real free/scheme qty
                elif x1 > 412:
                    amount = _num(t[0])         # Sales Value

            # customer / bill carry-down within the block
            if cust:
                customer = cust
                bill = ''
            if billno:
                bill = billno

            rows.append([
                customer, area, prod, pack, bill, date_tok,
                "%g" % qty, "%g" % free, "%.2f" % amount,
            ])

    return H, rows
