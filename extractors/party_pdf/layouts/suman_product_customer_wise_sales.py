import io
import re
from collections import defaultdict

import pdfplumber

# SUMAN PHARMA "Product-Customer Wise Sales".
#
# Same report family as BALAJI's klm_product_customerwise_sales but a DIFFERENT print
# geometry (station column at x0>=225, numeric cluster at x0>=400, no Pin Code column),
# so it gets its own positional parser. Product header carries down to per-customer
# rows; the 3 rightmost numerics are Qty, Free, Sales Value. sum(Value) reconciles
# EXACT to the printed GRAND TOTAL. Positional: re-opens the PDF bytes.

_STATION_X = 225
_NUM_X = 400


def parse_suman_product_customer_wise_sales(text, file_bytes=None):
    headers = ["Party Name", "Area", "Product Name", "Qty", "Free", "Amount"]
    rows = []
    if not file_bytes:
        return headers, rows
    cur_product = ""
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            lines = defaultdict(list)
            for w in page.extract_words():
                lines[round(w["top"])].append(w)
            for top in sorted(lines):
                ws = sorted(lines[top], key=lambda w: w["x0"])
                txt = " ".join(w["text"] for w in ws).strip()
                if not txt or set(txt.replace(" ", "")) <= set("-"):
                    continue
                if txt.startswith(("Customer Station", "Page No.", "SUMAN PHARMA",
                                   "KAMLA", "...Continued", "*****", "Powered By")):
                    continue
                if txt.startswith("GRAND TOTAL") or txt.startswith("TOTAL"):
                    continue                                   # oracles
                right = [w for w in ws if w["x0"] >= _NUM_X]
                nums = [w for w in right if re.fullmatch(r"-?[\d,]+\.?\d*", w["text"])]
                left = [w for w in ws if w["x0"] < _NUM_X]
                if len(nums) >= 3 and left:
                    qty = float(nums[-3]["text"].replace(",", ""))
                    free = float(nums[-2]["text"].replace(",", ""))
                    val = float(nums[-1]["text"].replace(",", ""))
                    party = " ".join(w["text"] for w in left if w["x0"] < _STATION_X).strip()
                    station = " ".join(w["text"] for w in left if w["x0"] >= _STATION_X).strip()
                    rows.append([party, station, cur_product, qty, free, val])
                else:
                    cur_product = txt
    return headers, rows
