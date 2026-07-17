import io
import re

import pdfplumber

from extractors.stock_pdf.parse_common import _to_number

_NUM = re.compile(r"^-?\d[\d,]*\.?\d*$")

# Header label (lowercased) -> canonical stock field. Anything NOT in this map
# (the month columns such as "mar"/"apr", or code/desc/packing) feeds no stock
# number, so the report can carry ANY number of month columns between Stock-Out
# and Sales without shifting the mapping — the columns are identified by their
# header text, never by a fixed position.
#
# Stock-Out reduces stock and Stock-In adds to it, so they occupy the only two
# remaining movement slots in the canonical sanity equation
# (closing = opening + purchase - purchase_return - sales + sales_return):
#   Stock-Out -> purchase_return (subtractive)   Stock-In -> sales_return (additive)
_LABEL_TO_FIELD = {
    "opening": "opening_stock",
    "purchase": "purchase_stock",
    "stock-out": "purchase_return",
    "sales": "sales_qty",
    "stock-in": "sales_return",
    "closing": "closing_stock",
    "stock-value": "closing_stock_value",
    "sales-value": "sales_value",
}


def _lines_by_top(page):
    words = page.extract_words(x_tolerance=1.5, y_tolerance=3)
    rows = {}
    for w in words:
        rows.setdefault(round(w["top"]), []).append(w)
    return [sorted(ws, key=lambda w: w["x0"]) for _, ws in sorted(rows.items())]


def parse_stock_in_out_statement(text, file_bytes=None):
    """A.B.PHARMA-style monthly 'Stock Statment'.

    Columns: Code | Item Description | Packing | Opening | Purchase | Stock-Out |
    <N month columns> | Sales | Stock-In | Closing | Stock-Value | Sales-Value.

    Header-driven: the column->field map is read from the header row's word
    x-positions, so 1..N month columns are handled transparently. Blank cells are
    common, so each number is bucketed by its x-position (not by token order).
    """
    if not file_bytes:
        return []
    records = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            lines = _lines_by_top(page)

            # ---- locate header row, build numeric column spans ----
            num_cols = None  # ordered list of (x0, field_or_None)
            pack_x = open_x = None
            for ws in lines:
                labels = {w["text"].lower(): w["x0"] for w in ws}
                if {"opening", "purchase", "closing"} <= labels.keys():
                    open_x = labels["opening"]
                    pack_x = labels.get("packing")
                    num_cols = [
                        (w["x0"], _LABEL_TO_FIELD.get(w["text"].lower()))
                        for w in ws
                        if w["x0"] >= open_x - 2
                    ]
                    break
            if not num_cols or open_x is None:
                continue

            def column_field(cx):
                for i, (x0, field) in enumerate(num_cols):
                    hi = num_cols[i + 1][0] if i + 1 < len(num_cols) else 1e9
                    if x0 <= cx < hi:
                        return field
                return None

            # ---- data rows: start with a numeric item code ----
            for ws in lines:
                if not ws or not ws[0]["text"].isdigit():
                    continue
                code = ws[0]["text"]
                name_parts, pack_parts, fields = [], [], {}
                for w in ws[1:]:
                    if w["x0"] < open_x - 2:  # text zone: name / packing
                        if pack_x is not None and w["x0"] >= pack_x - 2:
                            pack_parts.append(w["text"])
                        else:
                            name_parts.append(w["text"])
                        continue
                    if not _NUM.match(w["text"]):
                        continue
                    field = column_field((w["x0"] + w["x1"]) / 2)
                    if field:
                        val = _to_number(w["text"])
                        if val is not None:
                            fields[field] = val
                if not name_parts and not fields:
                    continue
                rec = {
                    "product_code": code,
                    "product_name": " ".join(name_parts),
                    "pack": " ".join(pack_parts),
                }
                rec.update(fields)
                records.append(rec)
    return records
