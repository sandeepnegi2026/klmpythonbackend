"""KAPOOR MEDICAL STORE — "PARTY+ITEM WISE SALE" (Marg billwise, positional).

Vendor : KAPOOR MEDICAL STORE (KMS), Mandi/Bilaspur (Himachal).
Title  : "PARTY+ITEM WISE SALE FROM dd/mm/yyyy TO dd/mm/yyyy"
Format : 13-page billwise detail. Body is a run of "PARTY NAME - <NAME> <TOWN>"
         bands, each followed by item rows. The flat text layer glues the
         QUANTITY digit onto the end of the ITEM NAME cell when the name is wide
         (e.g. "EKRAN SOFT SILICONE SUNSCREAM2" == item "…SUNSCREAM" + qty 2), so
         we parse POSITIONALLY off pdfplumber word x-coordinates instead.

Header (3 wrapped lines) -> columns and their word x-geometry (page 1):
   SNO            x0  ~9
   BILL NO.       x0  ~27   (GST-####)
   BILL DATE      x0  ~86   (dd/mm/yyyy)
   ITEM NAME      x0  144 .. ~258
   QUANTITY       x1  right-anchored ~285   (word center 261-290)
   FREE QTY       x0  ~293 .. ~316          (word center 290-318; often blank)
   EXPIRY DATE    x0  ~320   (dd/mm/yyyy)
   GROSS AMOUNT   x1  ~426
   NET AMOUNT     x1  ~479
   M.R.P.         x1  ~537   (per-unit MRP, kept as rate)

Column map:
   BILL NO.  -> invoice_number      BILL DATE -> invoice_date
   ITEM NAME -> product_name        QUANTITY  -> qty
   FREE QTY  -> free_qty            EXPIRY    -> expiry
   GROSS AMOUNT -> amount           NET AMOUNT -> net_amount
   M.R.P.    -> rate                PARTY NAME band -> party_name / party_location

Reconcile (last-page bare 4-number grand-total line):
   sum(qty)=2775  sum(free_qty)=154  sum(amount)=589205.82  sum(net_amount)=637766.89
No per-row balance equation for party reports; totals are the ground truth.
"""

import io
import re

import pdfplumber

H = ['Party Name', 'Area', 'Product Name', 'Invoice Number', 'Invoice Date',
     'Qty', 'Free', 'Expiry', 'Rate', 'Amount', 'Net Amount']

# x-column boundaries (centres), derived from header/data geometry above.
_ITEM_MAX = 258.0     # item words have centre < this
_QTY_MAX = 290.0      # QUANTITY column centre band: 258 .. 290
_FREE_MAX = 318.0     # FREE column centre band: 290 .. 318 (expiry starts ~320)

_DATE = re.compile(r'^\d{2}/\d{2}/\d{4}$')
_BILL = re.compile(r'^GST-\d+$', re.I)
_NUM = re.compile(r'^\d+(?:\.\d+)?$')
_INT = re.compile(r'^\d+$')

_PARTY = re.compile(r'^PARTY\s+NAME\s*-\s*(.+)$', re.I)


def _split_party(s):
    """`<NAME> [<AREA>] -<CITY>` or `<NAME> <TOWN>`.

    A trailing ` -<CITY>` segment (Marg town suffix) becomes party_location; the
    rest is party_name. When no ` -` is present the band is left whole as the
    name (the leading token is the customer, town is unreliable to peel)."""
    s = s.strip()
    if ' -' in s:
        name, loc = s.rsplit(' -', 1)
        return name.strip(' -'), loc.strip()
    return s, ''


def _num(tok):
    return tok if _NUM.match(tok) else ''


def parse_kapoor_party_itemwise_sale(text, file_bytes=None):
    rows = []
    if not file_bytes:
        return H, rows

    party = area = ''
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            words = page.extract_words(use_text_flow=False)
            # group words into visual lines by rounded 'top'
            lines = {}
            for w in words:
                key = round(w['top'] / 2.0)
                lines.setdefault(key, []).append(w)

            for key in sorted(lines):
                ws = sorted(lines[key], key=lambda w: w['x0'])
                s = ' '.join(w['text'] for w in ws).strip()
                if not s:
                    continue

                pm = _PARTY.match(s)
                if pm:
                    party, area = _split_party(pm.group(1))
                    continue

                low = s.lower()
                if low.startswith(('page no', 'printed by', 'kapoor medical',
                                   'party+item', 'sno', 'bill no', 'run date',
                                   'workstation', 'sale')):
                    continue

                # data row anchored on leading SNO + GST bill no
                if len(ws) < 4 or not _INT.match(ws[0]['text']):
                    continue
                if not (len(ws) > 1 and _BILL.match(ws[1]['text'])):
                    continue

                item_toks = []
                qty = free = ''
                bill = ''
                date = ''
                expiry = ''
                money = []   # (centre, value) after expiry
                seen_expiry = False

                for w in ws[1:]:            # skip SNO
                    t = w['text']
                    cx = (w['x0'] + w['x1']) / 2.0
                    if _BILL.match(t) and not bill:
                        bill = t
                        continue
                    if _DATE.match(t):
                        if not date:
                            date = t          # BILL DATE (first date)
                        elif not seen_expiry:
                            expiry = t         # EXPIRY DATE (second date)
                            seen_expiry = True
                        continue
                    if not seen_expiry:
                        # still in item / qty / free zone. A wide product name can
                        # spill (with the qty digit glued on) into the QUANTITY /
                        # FREE bands: those non-numeric spill-overs stay part of
                        # the item so the glued-qty peel below can recover them.
                        if cx < _ITEM_MAX:
                            item_toks.append(t)
                        elif cx < _QTY_MAX:
                            if _num(t):
                                qty = _num(t) or qty
                            else:
                                item_toks.append(t)
                        elif cx < _FREE_MAX:
                            if _num(t):
                                free = _num(t) or free
                            else:
                                item_toks.append(t)
                        else:
                            item_toks.append(t)
                    else:
                        v = _num(t)
                        if v:
                            money.append((cx, v))

                # glued-qty recovery: qty digit fused onto the last item word,
                # so the item word extends into the QTY band and no qty token
                # was captured. Peel the trailing digit run.
                if not qty and item_toks:
                    m = re.match(r'^(.*?)(\d+)$', item_toks[-1])
                    if m and m.group(1):
                        item_toks[-1] = m.group(1)
                        qty = m.group(2)

                product = ' '.join(item_toks).strip()
                # A genuine detail row is anchored by BILL NO + BILL DATE + EXPIRY
                # (two dates) + a product. Some source rows are sparse (only a
                # free qty and MRP print, gross/net absent) — keep them so the
                # printed grand totals reconcile; qty/money default to 0/blank.
                if not (bill and date and seen_expiry and product):
                    continue

                money.sort(key=lambda x: x[0])
                if len(money) >= 3:
                    gross, net, rate = money[0][1], money[1][1], money[2][1]
                elif len(money) == 2:
                    gross, net, rate = money[0][1], money[1][1], ''
                elif len(money) == 1:
                    # lone money value at the far-right MRP column is the rate
                    gross, net, rate = '', '', money[0][1]
                else:
                    gross = net = rate = ''

                rows.append([
                    party, area, product, bill, date,
                    qty or '0', free or '0', expiry, rate, gross, net,
                ])

    return H, rows
