import io
import re
from collections import defaultdict

import pdfplumber

# TRINITY PHARMACEUTICAL "PARTY + ITEM WISE SALE & SALE RETURN REPORT".
#
# Party band "PARTY NAME - <party> -<town>" -> item rows. Six numeric columns are
# right-edge (x1) anchored: SALE QTY, FREE QTY, FREE VALUE, RATE, G.AMOUNT, NET
# AMOUNT. Reconcile column = G. AMOUNT (reconciles EXACT to per-party subtotals +
# grand total). Item names may wrap across lines (pending_name). Rows whose G.AMOUNT
# cell is source-truncated are excluded by the printed subtotals and skipped.
# Positional: re-opens the PDF bytes.

_NUM = re.compile(r"^-?[\d,]+(?:\.\d+)?$")
_COLS = {"sale_qty": 292, "free_qty": 322, "free_value": 380,
         "rate": 427, "g_amount": 508, "net_amount": 590}
_TOL = 8


def _val(t):
    return float(t.replace(",", ""))


def _col_for(w):
    for name, x1 in _COLS.items():
        if abs(w["x1"] - x1) <= _TOL:
            return name
    return None


def parse_trinity_party_item_wise_sale(text, file_bytes=None):
    headers = ["Party Name", "Area", "Product Name", "Qty", "Free", "Rate", "Amount"]
    out = []
    if not file_bytes:
        return headers, out
    cur_party = cur_loc = ""
    pending_name = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            lines = defaultdict(list)
            for w in page.extract_words(use_text_flow=False, keep_blank_chars=False):
                lines[round(w["top"])].append(w)
            for top in sorted(lines):
                ws = sorted(lines[top], key=lambda w: w["x0"])
                text_line = " ".join(w["text"] for w in ws)
                if text_line.startswith(("TRINITY PHARMACEUTICAL", "PARTY + ITEM WISE", "Page No.",
                                         "Printed By", "SALE FREE", "SNO.")):
                    continue
                if text_line.strip() == "QTY QTY UNIT":
                    continue
                if text_line.startswith("COMPANY NAME"):
                    pending_name = []
                    continue
                if text_line.startswith("PARTY NAME"):
                    body = text_line[len("PARTY NAME - "):].strip()
                    m = re.search(r"\s-(?!.*\s-)(.+)$", body)
                    if m:
                        cur_loc = m.group(1).strip()
                        cur_party = body[:m.start()].strip()
                    else:
                        cur_party, cur_loc = body, ""
                    pending_name = []
                    continue
                cells = {}
                for w in ws:
                    if _NUM.match(w["text"]) and w["x0"] > 210:
                        c = _col_for(w)
                        if c and c not in cells:
                            cells[c] = w["text"]
                sno_word = ws[0]["text"]
                has_sno = bool(re.match(r"^-?\d+$", sno_word)) and ws[0]["x1"] <= 45
                name_frag = [w["text"] for w in ws if 52 <= w["x0"] < 210 and not _NUM.match(w["text"])]
                if "g_amount" in cells and not has_sno and not name_frag:
                    pending_name = []
                    continue                                   # subtotal / grand total
                if has_sno and "g_amount" in cells:
                    name = " ".join(pending_name + name_frag).strip()
                    out.append([cur_party, cur_loc, name,
                                _val(cells["sale_qty"]) if "sale_qty" in cells else "",
                                _val(cells["free_qty"]) if "free_qty" in cells else 0.0,
                                _val(cells["rate"]) if "rate" in cells else "",
                                _val(cells["g_amount"])])
                    pending_name = []
                elif name_frag and not cells:
                    pending_name += name_frag                  # wrapped item-name continuation
    return headers, out
