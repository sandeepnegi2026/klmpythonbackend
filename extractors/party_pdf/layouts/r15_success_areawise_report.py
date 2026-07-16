import io
import re
from collections import defaultdict

import pdfplumber

# ---------------------------------------------------------------------------
# SUCCESS PHARMAA & VACCINE (Coimbatore) "Areawise Sales Report" — a KLM
# sub-stockist, one file per KLM division (PEDIA, ...).
#
# Report furniture:
#   SUCCESS PHARMAA & VACCINE / <address> / "Areawise Sales Report" /
#   "From dd/mm/yy To dd/mm/yy for KLM <DIV>" / a dashed rule /
#   column header (all names TRUNCATED by the vendor's fixed-width printer):
#     "Area Name  Customer Name  Bill Dat  Bill Number  Product Name  Packi
#      Quan  Free  Repl  NetAmoun"
#   -> per-area / per-customer rows -> "Customer Sub Total" -> "Area Total"
#   -> a final "Grand Total <qty> <free> <amount>".
#
# GATE TOKEN (compact column-header run, unique to this vendor's truncated
# header): "productnamepackiquanfreereplnetamoun".
#
# Two quirks force a POSITIONAL (word x-coord) parse, not a regex over the flat
# text:
#   1) The flat-text columns Packi/Quan/Free/Repl print almost on top of each
#      other, so the space-delimited text is ambiguous. By x0 they are clean:
#        Product Name 214..277 | Packi 277..293 (never populated) |
#        Quan 293..320 | Free/Repl 320..340 | NetAmoun >=340 (right-aligned).
#      The paid quantity sits in the Quan column; the FREE quantity renders in
#      the "Repl" column slot (x0 ~334). Packi is always blank.
#   2) A line item that has free goods is split across TWO physical text lines:
#        line A: <Product> Quan=0  <Free in Repl slot>   (no amount)
#        line B: <Product> Quan=N                <Amount>  (no free)
#      Both belong to ONE sale. The free qty from line A is attached to the very
#      next paid (amount-bearing) line of the SAME product; the paid line's Quan
#      and Amount are taken verbatim (qty and value are NEVER derived from each
#      other).
#
# The whole logical report is DUPLICATED across every physical page of the PDF
# (each page is a byte-identical copy ending in its own "Grand Total"); parsing
# stops at the FIRST Grand Total so a single clean copy is emitted.
#
# Reconciles against the printed "Customer Sub Total" lines and the "Grand Total
# 242 77 31660.07" on the reference file (PEDIA): summed Qty=242, Free=77,
# Amount=31660.09 (the ~0.02 drift is the vendor's own subtotal rounding, e.g.
# MESSIA prints 224.99 for two 112.50 rows; the per-row amounts are exact).
# ---------------------------------------------------------------------------

H = ['Party Name', 'Area', 'Product Name', 'Bill No', 'Bill Date',
     'Qty', 'Free', 'Amount']

_MONEY = re.compile(r'^-?\d[\d,]*\.\d+$')
_INT = re.compile(r'^-?\d+$')

# Lead/context skip prefixes (matched on the area+customer text of a line).
_SKIP = ('area name', 'page number', 'document footer', 'from ',
         'areawise sales', 'success pharma', 'new no')
_SUBTOTAL = ('customer sub total', 'area total')


def _bucket(x0):
    """Map a word's left edge to a report column."""
    if x0 < 72:
        return 'area'
    if x0 < 148:
        return 'cust'
    if x0 < 175:
        return 'date'
    if x0 < 210:
        return 'bill'
    if x0 < 293:          # 214..277 product, 277..293 Packi (never populated)
        return 'prod'
    if x0 < 320:
        return 'quan'
    if x0 < 340:          # Free renders in the "Repl" column slot
        return 'free'
    return 'amt'


def parse_success_areawise_report(text=None, file_bytes=None):
    if not file_bytes:
        return H, []
    pdf = pdfplumber.open(io.BytesIO(file_bytes))
    rows = []
    area = party = bill = date = ''
    pending = None          # (product, free_qty) awaiting a paid line
    done = False
    for page in pdf.pages:
        if done:
            break
        lines = defaultdict(list)
        for w in page.extract_words():
            lines[round(w['top'])].append(w)
        for top in sorted(lines):
            cells = defaultdict(list)
            for w in sorted(lines[top], key=lambda x: x['x0']):
                cells[_bucket(w['x0'])].append(w['text'])
            area_t = ' '.join(cells.get('area', [])).strip()
            cust_t = ' '.join(cells.get('cust', [])).strip()
            date_t = ' '.join(cells.get('date', [])).strip()
            bill_t = ' '.join(cells.get('bill', [])).strip()
            prod = ' '.join(cells.get('prod', [])).strip()
            quan = cells.get('quan', [])
            free = cells.get('free', [])
            amt = cells.get('amt', [])

            low = (area_t + ' ' + cust_t).lower()
            # Each physical page repeats the whole report; stop at first Grand Total.
            if low.startswith('grand total'):
                done = True
                break
            if any(low.startswith(p) for p in _SKIP) or prod.lower().startswith('product name'):
                continue
            if any(low.startswith(p) for p in _SUBTOTAL):
                pending = None
                continue

            # Context carry-down.
            if area_t:
                area = area_t
            if cust_t:
                party = cust_t
            if date_t:
                date = date_t
            if bill_t:
                bill = bill_t

            if not prod:
                continue
            q = quan[0] if quan and _INT.match(quan[0]) else ''
            f = free[0] if free and _INT.match(free[0]) else ''
            a = amt[0].replace(',', '') if amt and _MONEY.match(amt[0]) else ''

            if a:
                fq = ''
                if pending and pending[0] == prod:
                    fq = pending[1]
                    pending = None
                elif f:
                    fq = f
                rows.append([party, area, prod, bill, date,
                             q or '0', fq or '0', a])
            elif f:
                # free-only line (no amount): stash for the next paid line
                pending = (prod, f)
    return H, rows
