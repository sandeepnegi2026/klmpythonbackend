import io
import re
from collections import defaultdict

import pdfplumber

# JAI AMBEY SALES "Customer Wise Sales(Detail)".
#
# HORIZONTAL PAGE-SPLIT layout: page 0 = text half (product/entry/date/batch), the
# numeric page = has 'Qty(Unit1)'+'Amount'. A single logical row is reconstructed by
# joining words from BOTH pages that share the same rounded top (y). A party-header
# row has ONLY a party name on the text half and carries the per-party subtotal on
# the numeric half with the 'Qty+Free' cell EMPTY (line items have it populated,
# x>=490). The 'All Customers' row is the grand total. sum(amount) reconciles EXACTLY
# to per-party subtotals + grand total. No Rate column is printed.
#
# Positional: needs word x-coordinates, so the parser re-opens the PDF bytes.

_MONEY = re.compile(r"^-?[\d,]+\.\d+$")


def _num(s):
    return float(s.replace(",", ""))


def parse_jai_ambey_customer_wise_sales(text, file_bytes=None):
    headers = ["Party Name", "Area", "Product Name", "Invoice No",
               "Invoice Date", "Qty", "Free", "Rate", "Amount"]
    out = []
    if not file_bytes:
        return headers, out

    rows = defaultdict(lambda: {"left": [], "right": []})
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            texts = [w["text"] for w in words]
            is_numeric = "Qty(Unit1)" in texts and "Amount" in texts
            side = "right" if is_numeric else "left"
            for w in words:
                rows[round(w["top"], 1)][side].append((w["x0"], w["text"]))

    current_party = ""
    header_seen = False
    for top in sorted(rows):
        left = sorted(rows[top]["left"], key=lambda c: c[0])
        right = sorted(rows[top]["right"], key=lambda c: c[0])
        joined_left = " ".join(t for _, t in left)
        if joined_left.startswith("Name To"):
            header_seen = True
            continue
        if not header_seen:
            continue                                   # repeated company banner
        qty = free = amount = qtyfree = None
        for x, t in right:
            if not _MONEY.match(t):
                continue
            if x < 130:
                qty = _num(t)
            elif 160 <= x < 240:
                free = _num(t)
            elif 250 <= x < 320:
                amount = _num(t)
            elif x >= 490:
                qtyfree = _num(t)
        if joined_left.strip() == "All Customers":
            continue                                   # grand-total row (oracle)
        if qtyfree is not None:
            prod = " ".join(t for x, t in left if x < 300)
            invoice = date = ""
            for x, t in left:
                if 300 <= x < 370:
                    invoice = t
                elif 370 <= x < 445:
                    date = t
            out.append([current_party, "", prod, invoice, date,
                        qty, free, "", amount])
        else:
            current_party = joined_left.strip()        # party-header row (subtotal)
    return headers, out
