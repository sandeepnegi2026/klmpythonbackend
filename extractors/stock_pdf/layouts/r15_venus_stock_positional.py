"""VENUS PHARMA "Stock and Sales report" — POSITIONAL rewrite.

Gate token (compact column-header run, spaces-stripped/lowercased):
    "op.purspsalessvalcr.db.adj.cstkcval"

The existing text-only ``venus_stock_statement`` parser collapses each row's
numbers into a dense list with ``_nums`` and then guesses which column each
belongs to by COUNT.  That is wrong for this format: every column
(Apr / May / Op. / Pur / SP / Sale / SS / SVal / Cr. / Db. / Adj. / C Stk /
C Val / Ord.) is independently blank-able, so a row with 5 present numbers and
a row with 12 present numbers must be read by X-COORDINATE, not by count.
Reading by count mislabels ``SVal`` (sales value) as ``sales_qty`` and
purchase as sales on most rows, so 92% of rows fail stock reconciliation even
though the SOURCE numbers reconcile perfectly.

This parser assigns every numeric word to a fixed column by its right edge
(numbers are right-aligned under each header). Column map (right edges from the
printed header, identical on every page):

    Apr 206 | May 235 | Op. 265 | Pur 296 | SP 320 | Sale 346 | SS 370 |
    SVal 410 | Cr. 434 | Db. 458 | Adj. 482 | C Stk 512 | C Val 546 | Ord. 576

Field mapping (qty and value kept strictly separate):
    Op.   -> opening_stock
    Pur   -> purchase_stock
    SP    -> purchase_free   (scheme/free-in)
    Sale  -> sales_qty
    SS    -> sales_free      (scheme/free-out)
    SVal  -> sales_value
    Cr.   -> sales_return    (+ slot)
    Db.   -> purchase_return (- slot; debit note reduces stock)
    Adj.  -> signed adjustment folded onto sales_return (+) / purchase_return (-)
    C Stk -> closing_stock
    C Val -> closing_stock_value

Reconcile identity holds on the source:
    opening + purchase + purchase_free - purchase_return
        - sales_qty - sales_free + sales_return = closing
"""

import re

import pdfplumber

from extractors.stock_pdf.parse_common import (
    _skip_line,
    _split_product_pack,
    _to_number,
)

GATE_TOKEN = "op.pursspalessvalcr.db.adj.cstkcval"

# Column right edges (x1) from the printed header row. A numeric word is
# assigned to the column whose right edge is closest to the word's right edge.
_COLS = [
    ("apr", 206.0),
    ("may", 235.0),
    ("op", 265.0),
    ("pur", 296.0),
    ("sp", 320.0),
    ("sale", 346.0),
    ("ss", 370.0),
    ("sval", 410.0),
    ("cr", 434.0),
    ("db", 458.0),
    ("adj", 482.0),
    ("cstk", 512.0),
    ("cval", 546.0),
    ("ord", 576.0),
]

_TOL = 14.0  # half a column pitch


def _assign_column(x1):
    best, bestd = None, 1e9
    for name, edge in _COLS:
        d = abs(x1 - edge)
        if d < bestd:
            best, bestd = name, d
    return best if bestd <= _TOL else None


def _num_word(t):
    """True when the token is a Venus numeric cell (may carry a trailing '.'
    and an optional leading '-')."""
    return bool(re.fullmatch(r"-?\d[\d,]*\.?", t))


def _is_division_line(s):
    return bool(re.match(r"^KLM\b", s, re.I))


def _is_noise_line(s):
    if re.match(
        r"^(Opening Value|Closing Value|Sales\s*:|Report Date|VENUS|Sales Value"
        r"|Credit|Debit|MG\d|Item Name|Stock and Sales|Page\b)",
        s,
    ):
        return True
    if "Purchase Value" in s or s.startswith("37,"):
        return True
    return False


def parse_venus_stock_positional(text, file_bytes=None):
    if file_bytes is None:
        return []
    records = []
    division = ""
    with pdfplumber.open(_as_stream(file_bytes)) as pdf:
        for page in pdf.pages:
            words = page.extract_words(use_text_flow=False)
            rows = {}
            for w in words:
                rows.setdefault(round(w["top"]), []).append(w)
            for top in sorted(rows):
                ws = sorted(rows[top], key=lambda w: w["x0"])
                text_line = " ".join(w["text"] for w in ws).strip()
                if _skip_line(text_line) or _is_noise_line(text_line):
                    continue
                if _is_division_line(text_line):
                    division = re.sub(r"\s+X[A-Z]\d+.*$", "", text_line).strip()
                    continue
                # numeric cells positioned in a data column
                cells = {}
                name_words = []
                for w in ws:
                    t = w["text"]
                    if _num_word(t) and w["x0"] > 185:
                        col = _assign_column(w["x1"])
                        if col:
                            cells[col] = _to_number(t) or 0.0
                            continue
                    # anything before the first data column is name/pack
                    if w["x1"] <= 190:
                        name_words.append(t)
                if not name_words:
                    continue
                # must have a closing stock and at least one flow to be a data row
                if "cstk" not in cells and "cval" not in cells:
                    continue
                prod_raw = " ".join(name_words).strip()
                name, pack = _split_product_pack(prod_raw)

                opening = cells.get("op", 0.0)
                purchase = cells.get("pur", 0.0)
                pur_free = cells.get("sp", 0.0)
                sale = cells.get("sale", 0.0)
                sale_free = cells.get("ss", 0.0)
                sval = cells.get("sval", 0.0)
                cr = cells.get("cr", 0.0)  # credit note -> inflow (+sr slot)
                db = cells.get("db", 0.0)  # debit note  -> outflow (-pr slot)
                adj = cells.get("adj", 0.0)  # signed adjustment

                sales_return = cr
                purchase_return = db
                if adj >= 0:
                    sales_return += adj
                else:
                    purchase_return += -adj

                r = {
                    "product_name": name,
                    "pack": pack,
                    "division": division,
                    "opening_stock": opening,
                    "purchase_stock": purchase,
                    "purchase_free": pur_free,
                    "purchase_return": purchase_return,
                    "sales_qty": sale,
                    "sales_free": sale_free,
                    "sales_return": sales_return,
                    "sales_value": sval,
                    "closing_stock": cells.get("cstk", 0.0),
                    "closing_stock_value": cells.get("cval", 0.0),
                }
                records.append(r)
    return records


def _as_stream(file_bytes):
    import io

    if isinstance(file_bytes, (bytes, bytearray)):
        return io.BytesIO(file_bytes)
    return file_bytes
