import io
import re

import pdfplumber

# JMV PHARMACEUTICALS "Party & Product Wise Sale" ("Sale").
#
# Fully columnar positional layout (Item Code | City | Party | Product | Packing |
# Qty | Free | Rate | Amount | Company | Salt | HSN). Each column assigned by word
# x-midpoint band. Amount (x 545-579) reconciles EXACT to the GRAND TOTAL. Positional:
# re-opens the PDF bytes.

_BOUNDS = [
    ("item_code", 0, 62), ("city", 62, 134), ("party", 134, 264),
    ("product", 264, 365), ("packing", 365, 413), ("qty", 413, 470),
    ("free", 470, 495), ("rate", 495, 545), ("amount", 545, 579),
    ("company", 579, 646), ("salt", 646, 713), ("hsn", 713, 10000),
]


def _col_for(xmid):
    for name, lo, hi in _BOUNDS:
        if lo <= xmid < hi:
            return name
    return None


def parse_jmv_party_product_city(text, file_bytes=None):
    headers = ["Party Name", "Area", "Product Name", "Qty", "Free", "Rate", "Amount"]
    rows = []
    if not file_bytes:
        return headers, rows
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            lines = {}
            for w in page.extract_words(use_text_flow=False, keep_blank_chars=False):
                lines.setdefault(round(w["top"]), []).append(w)
            for y in sorted(lines):
                ws = sorted(lines[y], key=lambda w: w["x0"])
                s = " ".join(w["text"] for w in ws).strip()
                low = s.lower()
                if s.upper().startswith("GRAND TOTAL"):
                    continue                                       # oracle
                if not s or s.startswith("---") or s == "Sale" or any(k in low for k in (
                        "continued", "end of report", "party & product",
                        "jmv pharmaceuticals", "h.no", "item code")):
                    continue
                cols = {name: [] for name, _, _ in _BOUNDS}
                for w in ws:
                    c = _col_for((w["x0"] + w["x1"]) / 2.0)
                    if c:
                        cols[c].append(w["text"])
                amt_s = " ".join(cols["amount"]).strip()
                qty_s = " ".join(cols["qty"]).strip()
                free_s = " ".join(cols["free"]).strip()
                if not re.match(r"^-?\d+(\.\d+)?$", amt_s) or not re.match(r"^-?\d+(\.\d+)?$", qty_s):
                    continue
                rows.append([
                    " ".join(cols["party"]).strip(),
                    " ".join(cols["city"]).strip(),
                    " ".join(cols["product"]).strip(),
                    float(qty_s),
                    float(free_s) if re.match(r"^-?\d+(\.\d+)?$", free_s) else 0.0,
                    " ".join(cols["rate"]).strip(),
                    float(amt_s),
                ])
    return headers, rows
