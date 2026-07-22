import io
import re
from collections import defaultdict

import pdfplumber

# MANISH AGENCIES "Product-Wise Customer-Wise Sales Summary".
#
# Product header (Prd.Code | Product Name | Pack) carries down to per-customer rows
# (Customer Name & Address | Qty | Free | Value). The 3 rightmost words (x0>=458) are
# Qty, Free, Value; Value reconciles EXACT to per-product 'Total:' + grand 'Total
# Value :'. Positional: re-opens the PDF bytes.

_X_PROD_NAME = 87.0
_X_PACK = 195.0
_X_CUST = 224.0
_X_QTY = 458.0


def _num(t):
    t = (t or "").strip().replace(",", "")
    return 0.0 if t in ("-", "") else float(t)


def parse_manish_product_customer_summary(text, file_bytes=None):
    headers = ["Party Name", "Area", "Product Name", "Qty", "Free", "Amount"]
    rows = []
    if not file_bytes:
        return headers, rows
    cur_name = cur_pack = ""
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            lines = defaultdict(list)
            for w in page.extract_words(use_text_flow=False, keep_blank_chars=False):
                lines[round(w["top"])].append(w)
            for top in sorted(lines):
                ws = sorted(lines[top], key=lambda w: w["x0"])
                texts = [w["text"] for w in ws]
                joined = " ".join(texts)
                if (joined.startswith("---") or joined.startswith("MANISH AGENCIES")
                        or joined.startswith("Product-Wise") or joined.startswith("Agency")
                        or joined.startswith("Prd.Code") or joined.startswith("Total Value")
                        or (texts and texts[0] == "Total:")):
                    continue
                num_ws = [w for w in ws if w["x0"] >= _X_QTY]
                left_ws = [w for w in ws if w["x0"] < _X_QTY]
                qty = free = value = None
                if len(num_ws) == 3:
                    qty, free, value = (w["text"] for w in num_ws)
                elif len(num_ws) == 2:
                    if num_ws[0]["text"] == "-":
                        free, value = num_ws[0]["text"], num_ws[1]["text"]
                    else:
                        qty, value = num_ws[0]["text"], num_ws[1]["text"]
                elif len(num_ws) == 1:
                    value = num_ws[0]["text"]
                prod_code = None
                pname_parts, pack_parts, cust_parts = [], [], []
                for w in left_ws:
                    x, t = w["x0"], w["text"]
                    if x < _X_PROD_NAME:
                        prod_code = t
                    elif x < _X_PACK:
                        pname_parts.append(t)
                    elif x < _X_CUST:
                        pack_parts.append(t)
                    else:
                        cust_parts.append(t)
                if prod_code is not None:
                    cur_name = " ".join(pname_parts).strip()
                    cur_pack = " ".join(pack_parts).strip()
                if not cust_parts or value is None:
                    continue
                cust_full = " ".join(cust_parts)
                m = re.match(r"^([A-Z]\d{3})\s+(.*)$", cust_full)
                caddr = m.group(2) if m else cust_full
                if "," in caddr:
                    pn, pl = caddr.split(",", 1)
                    party_name, party_location = pn.strip(), pl.strip()
                else:
                    party_name, party_location = caddr.strip(), ""
                rows.append([party_name, party_location, (cur_name + " " + cur_pack).strip(),
                             _num(qty), _num(free), _num(value)])
    return headers, rows
