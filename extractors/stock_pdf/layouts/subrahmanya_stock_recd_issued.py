"""Sri Subrahmanya Pharmaceuticals 'STOCK AND SALES STATEMENT' — positional.

Header (one row), division-banded (KLM <DIV>):
    Item Name  Pack  Opening  Received  Issued  Closing stock  Closing

Five right-aligned numeric columns. Interior cells (Received / Issued / the two
Closing cells) blank out for no-movement rows, so the printed token count per line
varies from 2 to 5 and a flat token parse cannot tell which column a lone number
belongs to — e.g. 'SOFIDEW RESYL-LOT 50ML 3 3' is Opening 3 / Issued 3 (closing 0),
while 'SOFIRASH-CREAM 30G 20 16 36' is Opening 20 / Received 16 / Closing 36. The
generic stock_simple_7col parser keeps ONLY the rows that print all five numbers
(~8 of ~30), dropping every sparse row. We therefore read word x-positions and bucket
each number into its column by matching the number's RIGHT edge (x1) to the header
label's right edge, clustering rows by top with a small tolerance.

'Closing stock' (4th) and the trailing 'Closing' (5th) print the same closing quantity
(51 and 51.00); we read closing from the 4th and fall back to the 5th. The last column
is NOT a rupee value — the per-row rupee totals appear only on the GroupTotal line.

Reconcile: closing = opening + received - issued  (Received is the purchase inflow,
Issued the sales outflow). Verified on the printed rows (DESOSOFT CREAM 19+34-2=51;
IMXIA-style rows included). Division bands ('KLM PEDICTRIC DIV'), 'GroupTotal :' lines,
the header, and the top value-summary block carry no name+number pair in the data
columns (or are name-filtered), so they never emit a record.
"""
import io
import re

import pdfplumber

from extractors.stock_pdf.parse_common import _skip_line, _split_product_pack

_NUM = re.compile(r"^-?[\d,]*\d(?:\.\d+)?$")
_NUM_MIN_X0 = 195.0   # data numbers start right of the Pack column (~226); name/pack sit left
_BIN_TOL = 40.0       # a number must fall within this of a column anchor to be placed


def _is_num(t):
    return bool(_NUM.match(t))


def _to_f(t):
    try:
        return float(t.replace(",", ""))
    except ValueError:
        return 0.0


def _cluster_rows(words, tol=4):
    rows, cur, base = [], [], None
    for w in sorted(words, key=lambda w: (round(w["top"]), w["x0"])):
        if base is None or abs(w["top"] - base) <= tol:
            base = w["top"] if base is None else base
            cur.append(w)
        else:
            rows.append(cur)
            cur, base = [w], w["top"]
    if cur:
        rows.append(cur)
    return rows


def _header_anchors(row):
    """Return {col: x1} for the 5 numeric columns, or None if this isn't the header."""
    op = rec = iss = stock = None
    closings = []
    for w in row:
        t = w["text"].lower()
        if t == "opening":
            op = w["x1"]
        elif t == "received":
            rec = w["x1"]
        elif t == "issued":
            iss = w["x1"]
        elif t == "stock":
            stock = w["x1"]
        elif t == "closing":
            closings.append(w["x1"])
    if op is None or rec is None or iss is None or not closings:
        return None
    # 'Closing stock' right edge = the 'stock' word; trailing 'Closing' = last one.
    return {
        "opening": op,
        "received": rec,
        "issued": iss,
        "closingstock": stock if stock is not None else closings[0],
        "closing": closings[-1],
    }


def parse_subrahmanya_stock_recd_issued(text, file_bytes=None):
    if not file_bytes:
        return []
    records = []
    anchors = None
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            for row in _cluster_rows(page.extract_words()):
                found = _header_anchors(row)
                if found:
                    anchors = found
                    continue
                if not anchors:
                    continue

                name_toks = [w["text"] for w in sorted(row, key=lambda w: w["x0"])
                             if w["x0"] < _NUM_MIN_X0]
                name_raw = " ".join(name_toks).strip()
                # Drop noise: the two division bands ('KLM <DIV>' — no digit, caught by
                # _skip_line and the DIV suffix), the 'GroupTotal :' line, and the
                # 'Powered by ...' footer. Everything else in the name column is a real
                # SKU, including zero-stock catalog rows (kept for completeness — they
                # print no numbers but are genuine products, not artifacts).
                if (not name_raw or _skip_line(name_raw)
                        or name_raw.lower().startswith(("grouptotal", "group total"))
                        or name_raw.upper().endswith(" DIV")):
                    continue

                col = {}
                for w in row:
                    if w["x0"] < _NUM_MIN_X0 or not _is_num(w["text"]):
                        continue
                    key, dist = min(
                        ((k, abs(x1 - w["x1"])) for k, x1 in anchors.items()),
                        key=lambda kv: kv[1],
                    )
                    if dist <= _BIN_TOL:
                        col[key] = _to_f(w["text"])

                op = col.get("opening", 0.0)
                rec = col.get("received", 0.0)
                iss = col.get("issued", 0.0)
                cl = col.get("closingstock", col.get("closing", 0.0))

                name, pack = _split_product_pack(name_raw)
                records.append({
                    "product_name": name or name_raw,
                    "pack": pack,
                    "opening_stock": op,
                    "purchase_stock": rec,
                    "purchase_free": 0.0,
                    "purchase_return": 0.0,
                    "sales_qty": iss,
                    "sales_free": 0.0,
                    "sales_return": 0.0,
                    "closing_stock": cl,
                })
    return records
