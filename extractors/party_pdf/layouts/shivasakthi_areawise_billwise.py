import io
import re

# ---------------------------------------------------------------------------
# SHREE SHIVASAKTHI MEDICAL AGENCIES (Erode) "Areawise Sales Report" — KLM
# sub-stockist, legacy DOS-style monospace ERP export (one file per KLM
# division: COSMO / COSMOCOR / COSMO-Q / DERMA / DERMACOR / PEDIA / PHARMA).
#
# This is a SIBLING of areawise_sales_billwise.py (JEYANTHI PHARMAA), same
# "Areawise Sales Report" title/ERP furniture, but a DIFFERENT column order:
# JEYANTHI is Product-first with a Customer COLUMN, whereas this export is
# BILL-NUMBER-first with the customer printed as a BAND heading. Hence a new
# module with its own detect gate.
#
# Report furniture (landscape, Courier New; Helvetica footer interleaved):
#   SHREE SHIVASAKTHI MEDICAL AGENCIES / <address> / "Areawise Sales Report" /
#   "From 01/06/26 To 30/06/26 for KLM <DIV>" / dashed rule /
#   header "Bill Number  Bill Date  P  Product Name  Packing  Quant  Freeq  D
#           Sale Value  Tax Amou  NetAmount  Rep" / dashed rule / then body.
#
# Body = CUSTOMER band -> bill/item rows -> "Customer Sub Total" -> a bare
# 7-numeric area/customer roll-up echo (skipped) -> next customer band; ends
# with a dashed rule, the bare-7-numeric Grand Total, another dashed rule and
# the page footer.
#
#   * A CUSTOMER band is a text line with NO trailing 7 numerics (e.g.
#     "SENTHIL PHARMACY, GOBI.", "AVR MEDICALS SANKARI."). The TOWN token
#     prints in its own x-band starting at x0 >= ~160; everything left of that
#     is the customer name. Customer is carried down its block.
#   * An ITEM row is either bill-anchored (^26[DR]\d{10} at x0=10) OR a
#     continuation item (no bill number, product P-code starts at x0 ~= 178).
#     Both carry exactly 7 right-aligned numeric tokens at x0 >= 420:
#       Quant, Freeq, D, Sale Value, Tax Amou, NetAmount, Rep.
#     Some rows carry no Bill Date and/or a blank product (continuation).
#   * "Customer Sub Total ..." and the bare-7-numeric echo directly after it
#     (area roll-up) are skipped, as are dashed rules and the Grand Total.
#
# Column map: Quant->qty, Freeq->free_qty, Sale Value->amount, Tax Amou->tax,
# NetAmount->net_amount (D and Rep kept as raw diagnostic columns). Freeq can
# be negative (sales returns), so free/qty may be signed.
#
# Reconciles EXACTLY against the printed "Grand Total" line on all 7 reference
# files: summed Quant / Freeq / Sale Value / Tax Amou / NetAmount equal the
# printed grand total (paise rounding only).
#
# Two page quirks (same as the JEYANTHI sibling): EVERY page's content stream
# holds the WHOLE report (page 1 chars span several page heights), so we read
# ONLY pdf.pages[0]; and the Helvetica footer glyph-interleaves with the body,
# so we keep only 'Courier' chars.
# ---------------------------------------------------------------------------

H = ['Party Name', 'Area', 'Product Name', 'Pack', 'Bill No', 'Bill Date',
     'Qty', 'Free', 'Amount', 'Tax', 'Net Amount']

_BILL = re.compile(r'^26[DR]\d{10}$')
_DATE = re.compile(r'^\d{2}/\d{2}/\d{2}$')
_NUM = re.compile(r'^-?[\d,]+(?:\.\d+)?$')

_TOWN_X0 = 160.0        # town token band start on customer bands
_NUM_X0 = 420.0         # trailing numeric columns start (right of Packing)
_CONT_X0 = 178.0        # continuation-item P-code x0 (no bill number)


def _num(t):
    try:
        return float(t.replace(',', ''))
    except (ValueError, AttributeError):
        return 0.0


def _fmt(v):
    return "%g" % v


def parse_shivasakthi_areawise_billwise(text, file_bytes=None):
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

        started = False
        dash_count = 0
        customer = ''
        area = ''
        after_subtotal = False   # bare-7-num lines here are roll-up echoes

        for y in sorted(lines):
            # rebuild words on this visual line from chars (space/gap split)
            cs = sorted(lines[y], key=lambda c: c['x0'])
            toks = []
            cur = None
            for c in cs:
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
            if not toks:
                continue

            joined = " ".join(t[0] for t in toks).strip()
            if not joined:
                continue

            # dashed rule -> 2nd one opens the data region
            if set(joined) <= set('- '):
                dash_count += 1
                if dash_count >= 2:
                    started = True
                continue
            if not started:
                continue

            if 'Customer Sub Total' in joined:
                after_subtotal = True   # following bare-7-num lines are echoes
                continue

            # trailing numeric tokens (columns right of Packing)
            nums = [t for t in toks
                    if t[1] >= _NUM_X0 and _NUM.match(t[0])]
            non_num = [t for t in toks if not _NUM.match(t[0])]

            # a bare-7-numeric line: after a Sub Total it is a customer/area
            # roll-up echo (or the final Grand Total) -> skip; BEFORE the Sub
            # Total (mid-block) it is a continuation item with a blank product.
            if len(nums) == 7 and not non_num:
                if after_subtotal:
                    continue
                # continuation item row (no bill, no product) — fall through

            first = toks[0]
            is_bill = _BILL.match(first[0]) is not None

            if len(nums) == 7:
                # ---- ITEM ROW ------------------------------------------
                after_subtotal = False
                bill = first[0] if is_bill else ''
                date = ''
                for t in toks:
                    if 100 <= t[1] < 175 and _DATE.match(t[0]):
                        date = t[0]
                        break
                # product = tokens between P-code col and Packing/number cols
                prod = " ".join(
                    t[0] for t in toks
                    if 185 <= t[1] < 375 and not _DATE.match(t[0])
                ).strip()
                pack = " ".join(
                    t[0] for t in toks if 375 <= t[1] < _NUM_X0
                ).strip()

                nums_sorted = sorted(nums, key=lambda t: t[1])
                vals = [_num(t[0]) for t in nums_sorted]
                qty, free, _d, sale, tax, net, _rep = vals

                rows.append([
                    customer, area, prod, pack, bill, date,
                    _fmt(qty), _fmt(free), "%.4f" % sale,
                    "%.4f" % tax, "%.4f" % net,
                ])
                continue

            # ---- CUSTOMER BAND (no trailing numerics) ------------------
            name = " ".join(t[0] for t in toks if t[1] < _TOWN_X0).strip()
            town = " ".join(t[0] for t in toks if t[1] >= _TOWN_X0).strip()
            if name:
                after_subtotal = False
                customer = name.rstrip(',').strip()
                area = town.rstrip(',.').strip()

    return H, rows
