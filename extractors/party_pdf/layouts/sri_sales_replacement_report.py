import io
from collections import defaultdict

import pdfplumber

# SRI SARAVANA PHARMA "Sales Replacement Report".
#
# Division/product/customer banded replacement (free-goods) report. Columns are
# positional (x-band). Pages are reprinted (duplicate body) so pages whose non-footer
# text signature repeats are skipped. A data row has a customer (x0 121-168), a date
# (169-196), a bill number (205-240) and a trailing value word (x0>=360). The row
# 'Grand Total' carries the printed oracle (rightmost value). sum(amount) reconciles
# EXACTLY to the Grand Total.
#
# Positional: needs word x-coordinates, so the parser re-opens the PDF bytes.


def _body_text_sig(page):
    toks = [w["text"] for w in page.extract_words() if w["top"] <= 560]
    txt = " ".join(toks)
    i = txt.find("Admin -")
    if i != -1:
        txt = txt[:i]
    return txt.strip()


def parse_sri_sales_replacement_report(text, file_bytes=None):
    headers = ["Party Name", "Area", "Product Name", "Invoice No",
               "Invoice Date", "Qty", "Free", "Rate", "Amount"]
    out = []
    if not file_bytes:
        return headers, out

    seen = set()
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            sig = _body_text_sig(page)
            if sig in seen:
                continue
            seen.add(sig)
            lines = defaultdict(list)
            for w in page.extract_words():
                lines[round(w["top"])].append(w)
            for top in sorted(lines):
                ws = sorted(lines[top], key=lambda x: x["x0"])
                joined = " ".join(w["text"] for w in ws)
                if joined.startswith("Grand Total"):
                    continue
                if joined.startswith(("Division Name", "Product Sub", "Division Sub",
                                      "Admin", "Document", "Page", "----", "From",
                                      "Sales", "SRI", "1A/1")):
                    continue
                has_cust = any(121 <= w["x0"] <= 168 for w in ws)
                has_date = any(169 <= w["x0"] <= 196 for w in ws)
                has_billno = any(205 <= w["x0"] <= 240 for w in ws)
                val_words = [w for w in ws if w["x0"] >= 360]
                if not (has_cust and has_date and has_billno and val_words):
                    continue
                division = " ".join(w["text"] for w in ws if w["x1"] <= 70).strip()
                product = " ".join(w["text"] for w in ws if 70 < w["x1"] <= 120).strip()
                party = " ".join(w["text"] for w in ws if 120 < w["x0"] <= 168).strip()
                date = next((w["text"] for w in ws if 169 <= w["x0"] <= 196), "")
                billno = next((w["text"] for w in ws if 205 <= w["x0"] <= 240), "")
                qty = next((w["text"] for w in ws if 244 <= w["x1"] <= 260 and w["x0"] >= 244), "")
                rate = next((w["text"] for w in ws if 265 <= w["x0"] <= 292), "")
                free = next((w["text"] for w in ws if 315 <= w["x1"] <= 328 and w["x0"] >= 315), "")
                amount = float(val_words[-1]["text"].replace(",", ""))
                out.append([party, division, product, billno, date, qty, free, rate, amount])
    return headers, out
