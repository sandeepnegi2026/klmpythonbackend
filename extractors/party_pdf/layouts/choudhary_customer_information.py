import io
import re

import pdfplumber

# CHOUDHARY DISTRIBUTORS "Customer Information" (SwilERP party sales).
#
# Positional. Section labels print truncated on their own line, value on the NEXT
# line: 'Custo' -> next line = <PARTY (x0<360)> <LOCATION (x0>=360)>; 'Produ' ->
# next line = <PRODUCT>. Then invoice data rows; a 'TOTA'(TOTAL) per-product line is
# the oracle. Column x0 buckets: BillNo x0<44 | BillDate 44-128 | SalesQty 128-160 |
# SalesVal 160-200 (amount). sum(SalesVal) reconciles EXACT to the TOTAL lines.
# Positional: re-opens the PDF bytes.


def _num(s):
    s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def parse_choudhary_customer_information(text, file_bytes=None):
    headers = ["Party Name", "Area", "Product Name", "Invoice No",
               "Invoice Date", "Qty", "Amount"]
    rows = []
    if not file_bytes:
        return headers, rows
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            lines = {}
            for w in page.extract_words(use_text_flow=False, keep_blank_chars=False):
                lines.setdefault(round(w["top"] / 3.0), []).append(w)
            ordered = [sorted(lines[k], key=lambda w: w["x0"]) for k in sorted(lines)]
            cur_cust = cur_loc = cur_prod = ""
            expect = None
            for lw in ordered:
                texts = [w["text"] for w in lw]
                first, fx = texts[0], lw[0]["x0"]
                if expect == "cust":
                    cur_cust = " ".join(w["text"] for w in lw if w["x0"] < 360).strip()
                    cur_loc = " ".join(w["text"] for w in lw if w["x0"] >= 360).strip()
                    expect = None
                    continue
                if expect == "prod":
                    cur_prod = " ".join(texts).strip()
                    expect = None
                    continue
                if first.startswith("Custo"):
                    expect = "cust"
                    cur_prod = ""
                    continue
                if first.startswith("Produ"):
                    expect = "prod"
                    continue
                if first.startswith("Bill") or first == "Qty.":
                    continue
                if first in ("M/S.CHOUDHURY", "Page", "Powered",
                             "165,MAHUTPARA,P.O-RANAGHAT,DIST-NADIA"):
                    continue
                if first.startswith("TOTA"):
                    continue                                    # printed oracle
                if _num(first) is not None and fx < 44:
                    date_t = sqty = sval = None
                    for w in lw[1:]:
                        x, t = w["x0"], w["text"]
                        if 44 <= x < 128:
                            date_t = t
                        elif 128 <= x < 160:
                            sqty = _num(t)
                        elif 160 <= x < 200:
                            sval = _num(t)
                    m = re.match(r"(\d{1,2}/\d{1,2}/\d{2,4})", date_t or "")
                    inv_date = m.group(1) if m else (date_t or "")
                    if sval is not None:
                        rows.append([cur_cust, cur_loc, cur_prod, first, inv_date, sqty, sval])
    return headers, rows
