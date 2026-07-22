import io
import re

import pdfplumber

# JACKSON DRUG HOUSE "Companywise Customerwise Sales Statement".
#
# Nested bands company > party -> invoice rows (product | Bill | Date | MRP | Qty |
# Rate | Amount). Amount = rightmost token (x0>=460), reconciles to Party/Patent/
# Grand totals. Lines are clustered by vertical CENTER (MRP/Qty/Rate sit ~0.35px
# above product/date/amount so round(top) would split a row). Positional: re-opens
# the PDF bytes.

_BILL_X0, _DATE_X0, _QTY_X0, _RATE_X0, _AMT_X0 = 137.0, 178.0, 388.0, 412.0, 460.0
_DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")
_NUM_RE = re.compile(r"^-?\d[\d,]*\.?\d*$")
_GLUE_TAIL_RE = re.compile(r"^(?P<prod>.*[A-Za-z])(?P<bill>\d[\dA-Za-z]*)$")


def _num(s):
    return float(s.replace(",", ""))


def _cluster_lines(words, tol=3.0):
    ws = sorted(words, key=lambda w: (w["top"], w["x0"]))
    lines = []
    for w in ws:
        c = (w["top"] + w["bottom"]) / 2.0
        for ln in lines:
            if abs(ln["c"] - c) <= tol:
                ln["toks"].append(w)
                ln["c"] = (ln["c"] * ln["n"] + c) / (ln["n"] + 1)
                ln["n"] += 1
                break
        else:
            lines.append({"c": c, "n": 1, "toks": [w]})
    lines.sort(key=lambda l: l["c"])
    for ln in lines:
        ln["toks"].sort(key=lambda t: t["x0"])
    return lines


def parse_jackson_companywise_customerwise_sales(text, file_bytes=None):
    headers = ["Party Name", "Area", "Product Name", "Invoice No",
               "Invoice Date", "Qty", "Free", "Rate", "Amount"]
    rows = []
    if not file_bytes:
        return headers, rows
    cur_party = ""
    next_band_is_company = True
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            for ln in _cluster_lines(page.extract_words()):
                toks = ln["toks"]
                text_line = " ".join(t["text"] for t in toks).strip()
                if not text_line:
                    continue
                if text_line.startswith(("Companywise Customerwise", "From :", "product Bill No",
                                         "JACKSON DRUG HOUSE", "Door No")):
                    continue
                if re.match(r"^Party Total\s*:", text_line):
                    cur_party = ""
                    continue
                if re.match(r"^Patent Total\s*:", text_line):
                    next_band_is_company = True
                    continue
                if re.match(r"^Gr[ao]nt Total\s*:", text_line):
                    continue
                has_date = any(_DATE_X0 - 8 <= t["x0"] <= _DATE_X0 + 30 and _DATE_RE.match(t["text"])
                               for t in toks)
                right = toks[-1]
                is_amt = right["x0"] >= _AMT_X0 and _NUM_RE.match(right["text"])
                if has_date and is_amt:
                    prod_toks = [t for t in toks if t["x1"] < _BILL_X0]
                    prod = " ".join(t["text"] for t in prod_toks)
                    bill = next((t["text"] for t in toks if _BILL_X0 - 2 <= t["x0"] < _DATE_X0 - 5), "")
                    if not bill and prod_toks and prod_toks[-1]["x1"] > 150:
                        m = _GLUE_TAIL_RE.match(prod_toks[-1]["text"])
                        if m:
                            bill = m.group("bill")
                            prod = " ".join([t["text"] for t in prod_toks[:-1]] + [m.group("prod")])
                    date = next((t["text"] for t in toks if _DATE_RE.match(t["text"])
                                 and _DATE_X0 - 8 <= t["x0"] <= _DATE_X0 + 30), "")
                    qty = next((t["text"] for t in toks if _QTY_X0 - 6 <= t["x0"] < _RATE_X0 - 2
                                and _NUM_RE.match(t["text"])), "")
                    rate = next((t["text"] for t in toks if _RATE_X0 - 4 <= t["x0"] < _AMT_X0
                                 and _NUM_RE.match(t["text"])), "")
                    rows.append([cur_party, "", prod, bill, date, qty, "", rate, _num(right["text"])])
                    continue
                if next_band_is_company:
                    next_band_is_company = False
                else:
                    cur_party = text_line
    return headers, rows
