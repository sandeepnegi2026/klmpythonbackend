import io
import re
from collections import defaultdict

import pdfplumber

# ASHA AGENCIES "Item Wise Summary of Sale By Party".
#
# Party-banded, per-item rows with GST columns. Detail row = dotted serial ('1.1')
# at the sr column (x0<100); its rightmost numeric is Amount (reconcile column,
# reconciles to 'Sub Total' + 'Grand Total'). A bare integer at the sr column is a
# party header (name may arrive as an un-numbered item-column line just above).
# Positional: re-opens the PDF bytes.


def _num(s):
    return float(s.replace(",", ""))


def parse_klm_item_wise_sale_by_party(text, file_bytes=None):
    headers = ["Party Name", "Area", "Product Name", "Qty", "Free", "Amount"]
    rows = []
    if not file_bytes:
        return headers, rows
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            lines = defaultdict(list)
            for w in page.extract_words(use_text_flow=False, keep_blank_chars=False):
                lines[round(w["top"])].append(w)
            pending_name = None
            cur_party = cur_area = ""
            for top in sorted(lines):
                ws = sorted(lines[top], key=lambda x: x["x0"])
                toks = [w["text"] for w in ws]
                if not toks:
                    continue
                joined = " ".join(toks)
                low = joined.lower()
                if toks[0].startswith("Mfr/Div:"):
                    continue
                if (low.startswith("sr. item name") or low.startswith("date from")
                        or joined.startswith("ASHA AGENCIES")
                        or low.startswith("item wise summary") or low.startswith("s/w support")):
                    continue
                first = ws[0]
                ftext = first["text"]
                if low.startswith("grand total") or low.startswith("sub total"):
                    continue                                    # printed oracles
                # detail row: dotted serial at sr column
                if re.fullmatch(r"\d+\.\d+", ftext) and first["x0"] < 100:
                    prod = [w["text"] for w in ws[1:] if w["x0"] < 240]
                    nums = [w for w in ws[1:] if w["x0"] >= 240
                            and re.fullmatch(r"[\d,]+(?:\.\d+)?", w["text"])]
                    if len(nums) < 3:
                        continue
                    rows.append([cur_party, cur_area, " ".join(prod),
                                 _num(nums[0]["text"]), _num(nums[1]["text"]),
                                 _num(nums[-1]["text"])])
                    continue
                # party header: bare integer at sr column
                if re.fullmatch(r"\d+", ftext) and first["x0"] < 100:
                    rest = [w["text"] for w in ws[1:]]
                    if pending_name:
                        cur_party = pending_name
                        cur_area = " ".join(rest).strip()
                        pending_name = None
                    elif len(rest) >= 2:
                        cur_party = " ".join(rest[:-1])
                        cur_area = rest[-1]
                    else:
                        cur_party = " ".join(rest)
                        cur_area = ""
                    continue
                # un-numbered item-column line = party NAME preceding its numbered area line
                if 100 <= first["x0"] < 240 and not any(
                        re.fullmatch(r"[\d,]+\.\d{2}", t) for t in toks):
                    pending_name = joined
                    continue
    return headers, rows
