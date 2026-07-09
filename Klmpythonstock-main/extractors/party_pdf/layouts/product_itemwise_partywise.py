import io
import re

import pdfplumber

_NUM = re.compile(r"^\d[\d,]*\.\d{2}$")
# skip page furniture (vendor / date / page / report title / column header)
_SKIP = re.compile(
    r"^[\s\-]*(amit pharma|from\b|page\b|sales report|particulars|master - cost)", re.I
)
# any subtotal/total line (S-Total, Grand Total, ...); may carry a leading "- "
_TOTAL_LINE = re.compile(r"\btotal\s*:", re.I)

# CLEAN right-hand numeric columns, keyed by word-center x. A.Qty / Fr.Qty sit
# just right of the Particulars column and get polluted by long addresses, so we
# do NOT read them — we DERIVE them (Amount = A.Qty*Rate, Free Val = Fr.Qty*Rate).
_COLS = [
    ("total", 370, 415),
    ("rate", 415, 450),
    ("mrp", 450, 492),
    ("amount", 492, 546),
    ("free_val", 546, 595),
]
_NAME_X = 292  # Particulars text lives left of this; numbers/overflow to the right


def _val(word):
    return float(word["text"].replace(",", "")) if _NUM.match(word["text"]) else None


def _bucket(cx):
    for name, lo, hi in _COLS:
        if lo <= cx < hi:
            return name
    return None


def _rows_by_baseline(page):
    words = sorted(page.extract_words(x_tolerance=1.5, y_tolerance=2), key=lambda w: (w["top"], w["x0"]))
    rows, cur, top0 = [], [], None
    for w in words:
        if top0 is None or w["top"] - top0 <= 6:  # name + numbers + MRP sub-line
            cur.append(w)
            top0 = top0 if top0 is not None else w["top"]
        else:
            rows.append(cur)
            cur, top0 = [w], w["top"]
    if cur:
        rows.append(cur)
    return rows


def parse_product_itemwise_partywise(text, file_bytes=None):
    """Marg 'Sales Report - Item Wise / Party Wise Summary' (AMIT PHARMA style).

    Product heading -> party rows (Particulars | A.Qty | Fr.Qty | Total Qty | Rate
    | MRP | Amount | Free Val) -> 'S-Total :'. Long party addresses overflow into
    the A.Qty/Fr.Qty columns and interleave in the text layer, so the row is read
    POSITIONALLY: the clean right columns (Rate/MRP/Amount/Free Val) by x-bucket,
    and A.Qty/Fr.Qty are DERIVED (Amount/Rate, Free-Val/Rate). Party name is the
    text left of the numeric zone, up to the first comma.
    """
    if not file_bytes:
        return [], []
    headers = ["Party Name", "Product Name", "Qty", "Free", "Rate", "Amount"]
    rows = []
    product = None
    product_rate = 0.0  # rate is constant per product; recover it for rate-polluted rows
    name_buf = ""  # wrapped party-address lines pending until their money line
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            for ws in _rows_by_baseline(page):
                ws = sorted(ws, key=lambda w: w["x0"])
                line = " ".join(w["text"] for w in ws)
                if _SKIP.match(line) or _TOTAL_LINE.search(line):
                    name_buf = ""
                    continue
                rights = {}
                for w in ws:
                    v = _val(w)
                    if v is None:
                        continue
                    b = _bucket((w["x0"] + w["x1"]) / 2)
                    if b:
                        rights[b] = v
                left_text = " ".join(
                    w["text"] for w in ws if w["x1"] < _NAME_X and not _NUM.match(w["text"])
                ).strip()

                if "amount" in rights:
                    # a party (money) row — Amount is the reliable right-most column;
                    # Rate can be eaten by a long address, so fall back to the
                    # product's rate. Name may span buffered wrapped lines.
                    particulars = f"{name_buf} {left_text}".strip()
                    name_buf = ""
                    party = particulars.split(",")[0].strip()
                    if not party or product is None:
                        continue
                    if rights.get("rate"):
                        product_rate = rights["rate"]
                    rate = rights.get("rate") or product_rate
                    amount = rights.get("amount") or 0.0
                    free_val = rights.get("free_val") or 0.0
                    a_qty = round(amount / rate, 2) if rate else (rights.get("total") or 0.0)
                    fr_qty = round(free_val / rate, 2) if rate else 0.0
                    rows.append([party, product, a_qty, fr_qty, rate, amount])
                elif left_text and "," not in left_text and ws[0]["x0"] < 40:
                    product = left_text  # product heading (never has a comma)
                    product_rate = 0.0
                    name_buf = ""
                elif left_text:
                    name_buf = f"{name_buf} {left_text}".strip()  # wrapped party address
    return headers, rows
