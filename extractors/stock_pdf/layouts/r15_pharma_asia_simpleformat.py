import io
import re

from extractors.stock_pdf.parse_common import _split_product_pack, _to_number

# ---------------------------------------------------------------------------
# PHARMA ASIA DISTRIBUTOR "Stock Statement (SimpleFormat)" — six numeric columns
# per row where several cells are printed BLANK, so the per-row number count
# varies (5, 6 or 7). The coarse `simple4` rule (opening/receipt/sales/closing)
# consumes the FIRST four numbers left-to-right and therefore folds the trailing
# rupee "Sales Value" into `closing_stock` on any row whose Receipt (or another)
# qty cell is blank -> ~71% false SANITY_FAILED.
#
# Masthead:  "PHARMA ASIA DISTRIBUTOR"
#            "Stock Statement (SimpleFormat)"
#            "KLM ( <DIVISION> ) <Mon>-<YY>"
#
# Single-line column header (printed once):
#   Code  Product Description  Packing  Opening  Receipt  Sales  Closing
#         Sales Value  Stock Value
#
# The six value columns are:
#   Opening (qty) | Receipt (purchase qty) | Sales (sales qty) | Closing (qty)
#   | Sales Value (rupee) | Stock Value (rupee = closing_stock_value)
#
# Because blank cells shift the token count, columns are placed POSITIONALLY by
# right-edge (x1): data is right-aligned, so each number is bound to the header
# value-column whose right edge it is closest to. qty and value stay separate;
# no quantity is ever derived from a rupee column.
#
# Gate token (compact, spaces stripped, lowercased column-header run):
#   "openingreceiptsalesclosingsalesvaluestockvalue"
# combined with the "(simpleformat)" banner. Corpus-unique to this export.
# ---------------------------------------------------------------------------

_NUM = re.compile(r"^-?[\d,]*\.?\d+$")

# Header value-column labels -> right-edge anchor key. "Sales Value" and
# "Stock Value" are two-word labels; we anchor each on its trailing "Value"
# token (and use the qty "Sales"/"Closing" for the qty columns). Anchors are
# re-derived from the header row on every page, so absolute x's need not be
# hard-coded.
_QTY_LABELS = ("Opening", "Receipt", "Closing")  # single-word qty headers


def _lines(words, tol=3.0):
    rows = {}
    for w in words:
        key = round(w["top"] / tol)
        rows.setdefault(key, []).append(w)
    return [sorted(v, key=lambda w: w["x0"]) for _, v in sorted(rows.items())]


def _v(t):
    if t is None or t in ("", "-"):
        return 0.0
    return _to_number(t) or 0.0


def _derive_anchors(ws):
    """From a header line, return the six value-column right edges in order
    [Opening, Receipt, Sales(qty), Closing, SalesValue, StockValue] or None."""
    texts = [w["text"] for w in ws]
    # Must look like the SimpleFormat header.
    if "Opening" not in texts or "Receipt" not in texts or "Closing" not in texts:
        return None
    if texts.count("Value") < 2 or "Sales" not in texts:
        return None

    opening = receipt = closing = None
    sales_qty = None
    value_edges = []
    for i, w in enumerate(ws):
        t = w["text"]
        if t == "Opening":
            opening = w["x1"]
        elif t == "Receipt":
            receipt = w["x1"]
        elif t == "Closing":
            closing = w["x1"]
        elif t == "Value":
            value_edges.append(w["x1"])
        elif t == "Sales":
            # The FIRST "Sales" (followed by "Closing") is the qty column; the
            # second "Sales" (followed by "Value") is the rupee header. The qty
            # one is the earlier x-position.
            if sales_qty is None:
                sales_qty = w["x1"]

    if None in (opening, receipt, closing, sales_qty) or len(value_edges) < 2:
        return None
    sales_value, stock_value = value_edges[0], value_edges[1]
    anchors = [opening, receipt, sales_qty, closing, sales_value, stock_value]
    # sanity: strictly increasing left-to-right
    if anchors != sorted(anchors):
        return None
    return anchors


def parse_r15_pharma_asia_simpleformat(text, file_bytes=None):
    if not file_bytes:
        return []
    import pdfplumber

    records = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        anchors = None  # [O, R, S, C, SV, STV] right edges
        for page in pdf.pages:
            words = page.extract_words()
            lines = _lines(words)

            # (re)derive header anchors on this page
            for ws in lines:
                a = _derive_anchors(ws)
                if a:
                    anchors = a
                    break
            if anchors is None:
                continue

            open_edge = anchors[0]
            # tolerance: half the smallest inter-column gap, capped, so a number
            # only binds when it is genuinely inside a value column.
            gaps = [anchors[i + 1] - anchors[i] for i in range(len(anchors) - 1)]
            tol = min(min(gaps) / 2.0 + 4.0, 22.0)

            for ws in lines:
                texts = [w["text"] for w in ws]
                # skip the header line and obvious noise
                if "Opening" in texts and "Receipt" in texts and "Closing" in texts:
                    continue
                line_text = " ".join(texts)
                if not re.search(r"[A-Za-z]{3}", line_text):
                    # grand-total footer line (only numbers) etc.
                    continue

                name_parts = []
                nums = []  # (idx, token)
                for w in ws:
                    t = w["text"]
                    if _NUM.match(t) and w["x0"] > open_edge - 30:
                        # inside the value band: bind to nearest anchor by right edge
                        idx = min(range(len(anchors)), key=lambda i: abs(anchors[i] - w["x1"]))
                        if abs(anchors[idx] - w["x1"]) <= tol:
                            nums.append((idx, t))
                    else:
                        # left of the value band -> part of code+name+pack
                        name_parts.append(t)

                if not name_parts:
                    continue

                # Every real product row begins with a numeric item Code
                # (2439, 2440, 6260 …). Masthead / banner / division-band lines
                # ("PHARMA ASIA DISTRIBUTOR", "Stock Statement (SimpleFormat)",
                # "KLM ( DERMA ) May-26") carry no leading code, so requiring one
                # drops that furniture without a keyword list.
                if not re.fullmatch(r"\d{2,6}", name_parts[0]):
                    continue
                name_parts = name_parts[1:]
                if not name_parts:
                    continue

                raw = " ".join(name_parts).strip()
                # strip Busy new-customer / marker asterisks at the head
                raw = raw.lstrip("*").strip()
                if not re.search(r"[A-Za-z]{2}", raw):
                    continue

                name, pack = _split_product_pack(raw)

                vals = {i: t for i, t in nums}
                # A real row must carry at least one qty cell (opening/closing) or
                # a value; pure-blank rows (all zero, product exists) are still
                # emitted with zeros so the catalog is captured.
                r = {
                    "product_name": name,
                    "pack": pack,
                    "opening_stock": vals.get(0, "0"),
                    "purchase_stock": vals.get(1, "0"),   # Receipt
                    "sales_qty": vals.get(2, "0"),        # Sales (qty)
                    "closing_stock": vals.get(3, "0"),    # Closing (qty)
                    "sales_value": vals.get(4, "0"),      # Sales Value (rupee)
                    "closing_stock_value": vals.get(5, "0"),  # Stock Value (rupee)
                }
                records.append(r)

    return records
