import io
import re

import pdfplumber

# MISHRA PHARMACEUTICALS "Company wise - Sales statement" (TWO-COLUMN variant).
#
# The page is split into two independent columns (L: x1<=305, R: x0>=305), each a
# self-contained "Product Name Packing Qty Free" run under KLM company bands and
# "<party>,<area>" party bands. A data row has product text + an integer Qty (in the
# column's qty x-band) + a decimal Amount. sum(Amount) reconciles to the running
# grand total printed on the 'Page No' footer. Shares the 'companywise-salesstatement'
# title with AMRIT but its doubled 'Product Name Packing Qty Free' header is distinct.
# Positional: re-opens the PDF bytes.

_AMT = re.compile(r"^[\d,]+\.\d{2}$")
_INT = re.compile(r"^\d+$")


def _to_num(s):
    return float(s.replace(",", ""))


def _cluster(words, tol=3.0):
    ws = sorted(words, key=lambda w: w["top"])
    lines, cur, ct = [], [], None
    for w in ws:
        if ct is None or abs(w["top"] - ct) <= tol:
            cur.append(w)
            ct = w["top"] if ct is None else ct
        else:
            lines.append(cur)
            cur, ct = [w], w["top"]
    if cur:
        lines.append(cur)
    return lines


def _is_company(toks):
    s = " ".join(toks)
    return (bool(re.match(r"^KLM(\(|\b)", s)) and not any(_AMT.match(t) for t in toks)
            and not any(_INT.match(t) for t in toks))


def _parse_col(words, side, rows):
    party = area = ""
    ql, qh, fl, fh = (210, 236, 238, 268) if side == "L" else (488, 514, 516, 542)
    for ws in _cluster(words):
        ws = sorted(ws, key=lambda w: w["x0"])
        toks = [w["text"] for w in ws]
        if any(w["text"] == "Page" for w in ws):
            continue
        amt = [w for w in ws if _AMT.match(w["text"])]
        if _is_company(toks):
            continue
        nonamt = [w for w in ws if not _AMT.match(w["text"])]
        if amt and not nonamt:
            continue                                       # subtotal
        if amt:
            has_int = any(_INT.match(w["text"]) for w in nonamt)
            has_text = any(re.search(r"[A-Za-z]", w["text"]) for w in nonamt)
            if has_int and has_text:
                amount = _to_num(amt[-1]["text"])
                qty = free = ""
                prod = []
                for w in ws:
                    if _AMT.match(w["text"]):
                        continue
                    if _INT.match(w["text"]) and ql <= w["x0"] <= qh:
                        qty = w["text"]
                        continue
                    if _INT.match(w["text"]) and fl <= w["x0"] <= fh:
                        free = w["text"]
                        continue
                    prod.append(w["text"])
                rows.append([party, area, " ".join(prod), qty, free, amount])
                continue
        if any(re.search(r"[A-Za-z]", t) for t in toks):
            s = " ".join(toks)
            if "," in s:
                nm, ar = s.split(",", 1)
                party, area = nm.strip(), ar.strip()
            else:
                party, area = s.strip(), ""


def parse_mishra_companywise_partywise_twocol(text, file_bytes=None):
    headers = ["Party Name", "Area", "Product Name", "Qty", "Free", "Amount"]
    rows = []
    if not file_bytes:
        return headers, rows
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            words = [w for w in page.extract_words() if w["top"] >= 70]
            left = [w for w in words if w["x1"] <= 305]
            right = [w for w in words if w["x0"] >= 305]
            _parse_col(left, "L", rows)
            _parse_col(right, "R", rows)
    return headers, rows
