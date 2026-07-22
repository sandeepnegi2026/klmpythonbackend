import io
import re

import pdfplumber

# ARCHI MEDICAL "CUSTOMER+ ITEM WISE SALE".
#
# Grouped by "CUSTOMER NAME - <party> -<location>"; per-item rows; per-customer
# subtotal lines (no SNO/item) + final grand total. Reconcile column = NET AMOUNT
# (x1 486-536). Qty is glue-prone so it is derived as TOTAL QTY - FREE QTY when the
# TOTAL QTY column is present. Positional: re-opens the PDF bytes.


def _num(s):
    return float(s.replace(",", ""))


def _col(w):
    x1, x0 = w["x1"], w["x0"]
    if 486 <= x1 <= 536:
        return "net"
    if 380 <= x1 <= 432:
        return "gross"
    if 305 <= x1 <= 327:
        return "totqty"
    if 250 <= x0 <= 278:
        return "freeqty"
    if 200 <= x1 <= 222 and x0 >= 206:
        return "saleqty"
    if x0 < 44:
        return "sno"
    return "item"


def _clean_product(tokens):
    txt = " ".join(tokens).strip()
    txt = re.sub(r"([A-Za-z]{1,3})\d+$", r"\1", txt)
    txt = re.sub(r"\b(?=[A-Za-z]*\d)(?=\d*[A-Za-z])[A-Za-z\d]{2,4}$",
                 lambda m: re.sub(r"\d", "", m.group(0)), txt)
    return re.sub(r"\s+", " ", txt).strip()


def parse_klm_customer_item_wise_sale(text, file_bytes=None):
    headers = ["Party Name", "Area", "Product Name", "Qty", "Free", "Amount"]
    rows = []
    if not file_bytes:
        return headers, rows
    cur_customer = cur_loc = ""
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            lines = {}
            for w in page.extract_words(use_text_flow=False, keep_blank_chars=False):
                lines.setdefault(round(w["top"]), []).append(w)
            for key in sorted(lines):
                ws = sorted(lines[key], key=lambda x: x["x0"])
                text_line = " ".join(w["text"] for w in ws)
                if text_line.startswith(("ARCHIE", "CUSTOMER+", "Page", "Printed", "SNO.")):
                    continue
                if text_line.startswith("CUSTOMER NAME -"):
                    body = text_line[len("CUSTOMER NAME -"):].strip()
                    if " -" in body:
                        name, loc = body.rsplit(" -", 1)
                    else:
                        name, loc = body, ""
                    cur_customer = name.strip()
                    cur_loc = loc.strip()
                    continue
                buckets = {}
                for w in ws:
                    buckets.setdefault(_col(w), []).append(w)
                if "net" not in buckets:
                    continue
                net = _num(buckets["net"][-1]["text"])
                if "sno" not in buckets and "item" not in buckets:
                    continue                                       # subtotal / grand total
                free = int(buckets["freeqty"][-1]["text"]) if "freeqty" in buckets else 0
                tot = int(buckets["totqty"][-1]["text"]) if "totqty" in buckets else None
                if tot is not None:
                    sale = tot - free
                else:
                    st = buckets.get("saleqty")
                    sale = int(st[-1]["text"]) if st and re.fullmatch(r"-?\d+", st[-1]["text"]) else ""
                item_txt = [t["text"] for t in buckets.get("item", [])]
                st = buckets.get("saleqty")
                if st and not re.fullmatch(r"-?\d+", st[-1]["text"]):
                    item_txt.append(st[-1]["text"])
                rows.append([cur_customer, cur_loc, _clean_product(item_txt), sale, free, net])
    return headers, rows
