import io
import re

import pdfplumber

# "Customer / Company / Itemwise Sales" report — Series-banded variant
# (MANISH MEDICAL / KLM). Distinct from `logic_erp` (which is the Sr.-column
# variant with decimal qty, dd-mm-yyyy dates and X-n-n invoices): this one has
# NO Sr column, integer qty, dd/mm/yyyy dates and VC/AC/KLM##### invoices, and
# is banded Location -> Series -> Party -> Company.
#
# Parsed POSITIONALLY (word x-coordinates) because the text layer can't be split
# reliably: the Code column carries internal spaces ("KLM 0004") and item names
# embed integers ("KLM FX 120 TAB", "COSMOQ AC 50 ...") which a right-anchored
# regex confuses with the integer Qty. Column x0 anchors (points), read from the
# header/data rows:
#   Code@22  Item@78  Packing@211  Batch@265  Qty@338  FQty@372  Rate@417
#   Amount@455  Inv.No@491  Inv.Date@536
_CODE_MAX = 76
_ITEM_MAX = 210
_PACK_MAX = 262
_BATCH_MAX = 336  # x0 >= this is the trailing numeric region

_DATE = re.compile(r"^\d{2}/\d{2}/\d{4}$")
_DEC = re.compile(r"^\d+\.\d{2}$")
_INT = re.compile(r"^\d+$")
_CTRL = re.compile(
    r"^(?:Location\s*:|Series\s*:|Total of|GRAND TOTAL|Customer\s*/|Code\s+Item|"
    r"Year\s*:|Page\b|Contact\b)",
    re.I,
)

H = [
    "Division",
    "Party Name",
    "Area",
    "Code",
    "Product Name",
    "Packing",
    "Batch No.",
    "Qty",
    "FQty",
    "Rate",
    "Amount",
    "Invoice No.",
    "Inv. Date",
]


def _cluster_lines(words):
    """Group words into physical lines by baseline (top within 3px)."""
    ws = sorted(words, key=lambda w: (round(w["top"]), w["x0"]))
    lines, cur, cur_top = [], [], None
    for w in ws:
        if cur_top is None or abs(w["top"] - cur_top) <= 3:
            cur.append(w)
            cur_top = w["top"] if cur_top is None else cur_top
        else:
            lines.append(sorted(cur, key=lambda x: x["x0"]))
            cur, cur_top = [w], w["top"]
    if cur:
        lines.append(sorted(cur, key=lambda x: x["x0"]))
    return lines


def _parse_data_row(line):
    """Return a row dict if this baseline-line is an item row, else None."""
    left = [w for w in line if w["x0"] < _BATCH_MAX]
    right = [w for w in line if w["x0"] >= _BATCH_MAX]
    if not left or not right:
        return None
    dates = [w["text"] for w in right if _DATE.match(w["text"])]
    decs = sorted((w["x0"], w["text"]) for w in right if _DEC.match(w["text"]))
    ints = sorted((w["x0"], w["text"]) for w in right if _INT.match(w["text"]))
    others = [
        w["text"]
        for w in right
        if not (_DATE.match(w["text"]) or _DEC.match(w["text"]) or _INT.match(w["text"]))
    ]
    # A genuine item row: exactly 1 date, >=2 decimals (rate, amount), >=1 int
    # (qty [, fqty]) and exactly one non-numeric token (the invoice no.).
    if len(dates) != 1 or len(decs) < 2 or len(ints) < 1 or len(others) != 1:
        return None
    code = " ".join(w["text"] for w in left if w["x0"] < _CODE_MAX)
    item = " ".join(w["text"] for w in left if _CODE_MAX <= w["x0"] < _ITEM_MAX)
    pack = " ".join(w["text"] for w in left if _ITEM_MAX <= w["x0"] < _PACK_MAX)
    batch = " ".join(w["text"] for w in left if _PACK_MAX <= w["x0"] < _BATCH_MAX)
    if not code and not item:
        return None
    return [
        code,
        item,
        pack,
        batch,
        ints[0][1],
        ints[1][1] if len(ints) >= 2 else "0",
        decs[0][1],
        decs[-1][1],
        others[0],
        dates[0],
    ]


def parse_customer_itemwise_series(text, file_bytes=None):
    if not file_bytes:
        return H, []
    rows = []
    cur_party = cur_area = cur_div = ""
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            for line in _cluster_lines(page.extract_words(x_tolerance=1.5)):
                joined = " ".join(w["text"] for w in line).strip()
                if not joined:
                    continue
                dr = _parse_data_row(line)
                if dr:
                    rows.append([cur_div, cur_party, cur_area] + dr)
                    continue
                if _CTRL.match(joined):
                    continue
                # Party band "<code> - <name> , <area>" (has a comma) vs company
                # band "KLM LABORA - <division>" (no comma).
                m = re.match(r"^(.*?)\s-\s(.+)$", joined)
                if m:
                    rest = m.group(2)
                    if "," in rest:
                        name, area = rest.split(",", 1)
                        cur_party = name.strip()
                        cur_area = area.strip(" .,")
                    else:
                        cur_div = rest.strip()
    return H, rows
