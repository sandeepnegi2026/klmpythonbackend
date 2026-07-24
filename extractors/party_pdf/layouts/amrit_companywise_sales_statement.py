import io
import re
from collections import defaultdict

import pdfplumber

# AMRIT PHARMACEUTICALS "Company wise - Sales statement" (billwise, per-party).
#
# Company band -> party band (line with a comma) -> product line -> data rows. Data
# row starts with a bill token ([A-Z]?digits) at x0<55 and has >=6 positional cells:
#   Bill | Date+Batch | Ex.Dt | PTR | MRP | Qty | Free | Amount (rightmost).
# The rightmost Amount reconciles EXACTLY to the printed grand total (a lone number
# echoed in the amount column). Shares the 'companywise-salesstatement' title with
# MISHRA but its column header (Bill No Date Batch...) is distinct.
#
# Positional: needs word x-coordinates, so the parser re-opens the PDF bytes.

_DATE_BATCH = re.compile(r"^(\d{2}/\d{2}/\d{4})(.*)$")
_BILL = re.compile(r"^[A-Z]?\d{3,}$")
_NUM = re.compile(r"^\d[\d,]*\.?\d*$")


def _f(s):
    return s.replace(",", "") if s else ""


def parse_amrit_companywise_sales_statement(text, file_bytes=None):
    headers = ["Party Name", "Product Name", "Invoice No", "Invoice Date",
               "Qty", "Free", "Rate", "Amount"]
    out = []
    if not file_bytes:
        return headers, out

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            byrow = defaultdict(list)
            for w in page.extract_words():
                byrow[round(w["top"])].append(w)
            company = None
            party = ""
            pending_product = ""
            for t in sorted(byrow):
                ws = sorted(byrow[t], key=lambda w: w["x0"])
                line = " ".join(w["text"] for w in ws)
                low = line.lower()
                if (line.startswith("AMRIT PHARMACEUTICALS") or low.startswith("company wise")
                        or low.startswith("bill no date") or line.strip() == "Amount"
                        or low.startswith("page no")):
                    continue
                first = ws[0]
                is_data = bool(_BILL.match(first["text"])) and first["x0"] < 55 and len(ws) >= 2
                if is_data:
                    cols = {k: None for k in
                            ("bill", "datebatch", "exdt", "ptr", "mrp", "qty", "free", "amount")}
                    for w in ws:
                        x, tt = w["x0"], w["text"]
                        if x < 55:
                            cols["bill"] = tt
                        elif x < 126:
                            cols["datebatch"] = tt
                        elif x < 160:
                            cols["exdt"] = tt
                        elif x < 190:
                            cols["ptr"] = tt
                        elif x < 218:
                            cols["mrp"] = tt
                        elif x < 245:
                            cols["qty"] = tt
                        elif x < 262:
                            cols["free"] = tt
                        else:
                            cols["amount"] = tt
                    m = _DATE_BATCH.match(cols["datebatch"] or "")
                    out.append([party, pending_product, cols["bill"],
                                m.group(1) if m else "", _f(cols["qty"]), _f(cols["free"]),
                                _f(cols["ptr"]), _f(cols["amount"])])
                    pending_product = ""
                    continue
                if len(ws) == 1 and _NUM.match(ws[0]["text"].replace(",", "")) and ws[0]["x0"] >= 262:
                    continue                                   # grand-total echo (oracle)
                if "," in line:
                    party = line
                elif company is None:
                    company = line
                else:
                    pending_product = line
    return headers, out
