import io
import re

from extractors.stock_pdf.parse_common import _split_product_pack, _to_number

# ---------------------------------------------------------------------------
# "PRODUCT WISE STOCK AND SALE -WITH PROFIT" (VIJAY MEDICAL AGENCIES, Jassur)
# — Marg ruled register, banded by "COMPANY NAME - KLM <DIV>".
#
# Wrapped 3-line column header:
#   PACK/  OPENING             SALE VALUE   CLOSING  CLOSING VALUE
#   SNO. ITEM NAME  PURCHASE-1 NET SALE-1
#   SIZE   STOCK-1             TOTAL        STOCK    (PUR RATE)
#
# Numeric cells are RIGHT-ALIGNED and BLANK WHEN ZERO, so the flat text carries
# 3-6 numbers per row with no way to tell which column each belongs to (the
# n_rects -> marg_bordered route mis-mapped them: false SANITY_FAILED). This
# parser re-reads word x-coordinates via pdfplumber and assigns every numeric
# word to the NEAREST column right-edge taken from the header words.
#
# Verified identity Opening + Purchase - Sale = Closing on reference rows
# (EKRAN AQUA: 85+15-58=42; COSMOQ OC: 50-3=47). Some rows still break the
# identity in the SOURCE file itself (free/replacement outflow is not printed
# as a column) — that is a report limitation, not a parse defect.
# ---------------------------------------------------------------------------

_NUM = re.compile(r"^-?[\d,]+(?:\.\d+)?$")
_FURNITURE = re.compile(
    r"company name|page no|printed by|product wise stock|workstation|run date", re.I
)

# column order: opening, purchase, sales_qty, sales_value, closing, closing_value
_HDR_ANCHORS = (
    ("STOCK-1", 0), ("PURCHASE-1", 1), ("SALE-1", 2),
    ("TOTAL", 3), ("STOCK", 4), ("RATE)", 5),
)
_KEYS = ("opening_stock", "purchase_stock", "sales_qty",
         "sales_value", "closing_stock", "closing_stock_value")


def _lines(words, tol=3.0):
    rows = {}
    for w in words:
        key = round(w["top"] / tol)
        rows.setdefault(key, []).append(w)
    return [sorted(v, key=lambda w: w["x0"]) for _, v in sorted(rows.items())]


def parse_product_wise_stock_sale_profit(text, file_bytes=None):
    if not file_bytes:
        return []
    import pdfplumber

    records = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        col_r = None
        for page in pdf.pages:
            words = page.extract_words()
            lines = _lines(words)
            # column right-edges from the header words (re-derived per page;
            # 'STOCK'/'TOTAL' are matched only on the header lines, keyed off
            # the unambiguous PURCHASE-1 / STOCK-1 anchors)
            hdr = {}
            for ws in lines:
                texts = [w["text"] for w in ws]
                if "PURCHASE-1" in texts or "STOCK-1" in texts or "RATE)" in texts:
                    for w in ws:
                        hdr.setdefault(w["text"], []).append(w["x1"])
            if all(k in hdr for k, _ in _HDR_ANCHORS[:3]):
                col_r = [0.0] * 6
                col_r[0] = hdr["STOCK-1"][0]
                col_r[1] = hdr["PURCHASE-1"][0]
                col_r[2] = hdr["SALE-1"][0]
                col_r[3] = hdr.get("TOTAL", [400])[0]
                col_r[4] = hdr.get("STOCK", [465])[-1]
                col_r[5] = hdr.get("RATE)", [550])[-1]
            if col_r is None:
                continue
            for ws in lines:
                line_text = " ".join(w["text"] for w in ws)
                if _FURNITURE.search(line_text):
                    continue
                nums, name_parts = [], []
                for w in ws:
                    if _NUM.match(w["text"]):
                        nums.append(w)
                    elif w["x0"] < col_r[0] - 15:
                        name_parts.append(w["text"])
                if not nums or not name_parts:
                    continue
                # leading SNO is the first bare integer hugging the left margin
                if name_parts and name_parts[0].isdigit():
                    name_parts = name_parts[1:]
                name = " ".join(name_parts)
                if not re.search(r"[A-Za-z]{3}", name):
                    continue  # band totals / stray fragments
                vals = {}
                for w in nums:
                    if w["x0"] < 32 and w["text"].isdigit():
                        continue  # SNO extracted as a numeric word
                    idx = min(range(6), key=lambda i: abs(col_r[i] - w["x1"]))
                    if abs(col_r[idx] - w["x1"]) <= 25 and idx not in vals:
                        vals[idx] = _to_number(w["text"]) or 0.0
                if not vals:
                    continue
                pname, pack = _split_product_pack(name)
                rec = {"product_name": pname, "pack": pack}
                for i, key in enumerate(_KEYS):
                    rec[key] = vals.get(i, 0.0)
                records.append(rec)
    return records
