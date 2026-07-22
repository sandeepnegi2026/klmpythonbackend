import io
import re

import pdfplumber

# RAVIRA MEDICAL AGENCIES "Customer And Company Sales" (bill-level).
#
# Customer band "Customer :<name> Add :<area>" -> invoice rows
#   <INV [A-Z]{1,3}\d{3,}> <DD/MM/YYYY> <product> <pack> <batch> <qty> <free> <amount>
# with the numeric columns right-anchored (amount x1>430, free x1>395, qty x1>355).
# Amount reconciles EXACT to per-party 'Total:' + 'Grand Total'. Positional: re-opens
# the PDF bytes.


def parse_ravira_customer_company_sales(text, file_bytes=None):
    headers = ["Party Name", "Area", "Product Name", "Invoice No",
               "Invoice Date", "Qty", "Free", "Rate", "Amount"]
    rows = []
    if not file_bytes:
        return headers, rows
    cur_party = cur_loc = ""
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for pg in pdf.pages:
            lines = {}
            for w in pg.extract_words():
                lines.setdefault(round(w["top"]), []).append(w)
            for key in sorted(lines):
                lw = sorted(lines[key], key=lambda w: w["x0"])
                txt = " ".join(w["text"] for w in lw)
                if txt and set(txt.replace(" ", "")) <= set("-"):
                    continue
                if lw[0]["text"] == "Customer" or txt.startswith("Customer :"):
                    m = re.search(r"Customer :(.*?)\s+Add :(.*)$", txt)
                    if m:
                        cur_party, cur_loc = m.group(1).strip(), m.group(2).strip()
                    else:
                        m2 = re.search(r"Customer :(.*)$", txt)
                        cur_party, cur_loc = (m2.group(1).strip() if m2 else ""), ""
                    continue
                if lw[0]["text"] == "Total:" or txt.startswith("Grand Total"):
                    continue                                   # printed oracles
                if (re.match(r"^[A-Z]{1,3}\d{3,}$", lw[0]["text"]) and len(lw) >= 2
                        and re.match(r"\d{2}/\d{2}/\d{4}", lw[1]["text"])):
                    inv, date = lw[0]["text"], lw[1]["text"]
                    amount = free = qty = ""
                    prod_words = []
                    for w in lw[2:]:
                        t = w["text"].replace(",", "")
                        x1 = w["x1"]
                        if re.fullmatch(r"-?\d+\.\d{2}", t):
                            if x1 > 430:
                                amount = float(t)
                            elif x1 > 395:
                                free = float(t)
                            elif x1 > 355:
                                qty = float(t)
                            else:
                                prod_words.append((w["x0"], w["text"]))
                        else:
                            prod_words.append((w["x0"], w["text"]))
                    prod = " ".join(t for x0, t in prod_words if x0 < 287).strip()
                    rows.append([cur_party, cur_loc, prod, inv, date, qty, free, "", amount])
    return headers, rows
