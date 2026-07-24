import io
import re

import pdfplumber

# NAGAMMAI PHARMA "Customer Purchase-Divisionwise Report".
#
# Party-banded billwise report. Structure (per party):
#   <PARTY NAME + TOWN embedded>                         <- party header (far-left text)
#   <DD/MM/YY> <BillNumber> <Product...> <Pack> <Batch> <Exp> <Qty> [<Free>] <Rate> <Gross Amount>
#   ...
#   <qty> [<free>] <amount>                              <- per-party subtotal (x0>=200, numeric)
#   ... (repeats) ... <grand qty> <grand amount>         <- grand total (glyph-corrupted)
#
# POSITIONAL: columns are right-aligned and their x0 shifts with digit count, so
# they MUST be bucketed by right edge (x1): qty x1~[250-258], free ~[277-286],
# rate ~[301-309], amount ~[336-344]. The row AMOUNT is READ from the amount band
# (0 for fully-free rows). sum(amount) reconciles to each per-party subtotal to
# the paisa (<=0.01); the printed GRAND TOTAL is glyph-corrupted ('500. 27
# 217211.91') and off by <=0.06 (vendor rounding) — the per-party subtotal is the
# true oracle (cf. JAYASRI/ZISHAN).
#
# REPLICATION TRAP: pdfplumber reports ~10 physical pages but EVERY physical page's
# text is the ENTIRE report (Page Number 1/6 .. 6/6). Parse ONLY pdf.pages[0] — it
# holds the whole document exactly once; iterating all pages would 10x-count.
#
# Positional: needs word x-coordinates, so the parser re-opens the PDF bytes.

_DATE = re.compile(r"^\d{2}/\d{2}/\d{2}$")
_NUM = re.compile(r"^-?\d+\.?\d*$")
# The column header reprints at every mid-report page break. On the FIRST break it
# comes out glyph-GARBLED and split across two reconstructed lines:
#   'BilDl oDcautm Beinllt FNuomobteerr T e x tProduct'   (garbled 'Bill Document Number Text')
#   'Name Pack Batch Expir Qty Fre Rep Rate Gross Amo Page 1 / 10'
# Both must be treated as noise so the active party carries across the page break
# (otherwise the garbled line is mistaken for a party heading and splits one party's
# rows). 'Pack Batch Expir' catches the clean header + the 2nd garbled line;
# 'FNuomobteerr' catches the 1st garbled line (the garble is identical on every file).
_HEADER_SUBSTR = ("NAGAMMAI PHARMA", "(DIVISION OF KALAYANI", "Customer Purchase-Divisionwise",
                  "for KLM", "Bill Dat Bill Number", "Pack Batch Expir", "FNuomobteerr",
                  "Page Number", "Document Footer")


def _bucket(x1):
    if 250 <= x1 <= 258:
        return "qty"
    if 277 <= x1 <= 286:
        return "free"
    if 301 <= x1 <= 309:
        return "rate"
    if 336 <= x1 <= 344:
        return "amount"
    return None


def _num(s):
    s = s.strip()
    return "0" if s in ("", "-") else s


def _is_noise(txt):
    return (any(h in txt for h in _HEADER_SUBSTR)
            or re.match(r"^-{20,}$", txt.strip())
            or txt.startswith("From 01/"))


def parse_klm_nagammai_customer_purchase_divisionwise(text, file_bytes=None):
    headers = ["Party Name", "Invoice Date", "Invoice No", "Product Name",
               "Qty", "Free", "Rate", "Amount"]
    rows = []
    if not file_bytes:
        return headers, rows

    from collections import defaultdict
    party = ""
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        page = pdf.pages[0]                     # page 0 holds the whole report exactly once
        words = page.extract_words(use_text_flow=False)
    lines = defaultdict(list)
    for w in words:
        lines[round(w["top"])].append(w)
    for top in sorted(lines):
        ws = sorted(lines[top], key=lambda w: w["x0"])
        txt = " ".join(w["text"] for w in ws)
        if not txt.strip() or _is_noise(txt):
            continue
        # DATA ROW: a date at the far left
        if _DATE.match(ws[0]["text"]) and ws[0]["x0"] < 40:
            date = ws[0]["text"]
            billno = ws[1]["text"] if len(ws) > 1 else ""
            cols = {}
            for w in ws:
                b = _bucket(w["x1"])
                if b and _NUM.match(w["text"]):
                    cols.setdefault(b, w["text"])
            prod = " ".join(w["text"] for w in ws[2:] if w["x1"] < 250)
            rows.append([party, date, billno, prod,
                         _num(cols.get("qty", "0")), _num(cols.get("free", "0")),
                         _num(cols.get("rate", "0")), _num(cols.get("amount", "0"))])
            continue
        # SUBTOTAL / GRAND TOTAL: numeric block sitting to the right — skip (oracle only)
        if ws[0]["x0"] >= 200 and all(_NUM.match(w["text"]) or w["text"] == "-" for w in ws):
            continue
        # otherwise: PARTY HEADER (town/area embedded in the name)
        party = txt.strip()
    return headers, rows
