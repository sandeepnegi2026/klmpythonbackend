"""PHARMA ASIA DISTRIBUTOR 'Stock Statement' — KLM (<DIV>) coded 6-column export.

Vendor:  PHARMA ASIA DISTRIBUTOR (KLM divisions; e.g. 'KLM ( DERMA ) Jun-26').
File:     '.../PHARMA ASIA DISTRIBUTORS/Stock report/KLM DERMA.pdf'

Header (printed once at the top of the section):

    Code  Product Description  Packing  Opening  Receipt  Sales  Closing  Sales Value  Stock Value

SIX numeric columns after the (glyph-scrambled) Product Description + Packing text:
    Opening      -> opening_stock
    Receipt      -> purchase_stock
    Sales        -> sales_qty
    Closing      -> closing_stock
    Sales Value  -> sales_value          (money — NOT a quantity)
    Stock Value  -> closing_stock_value  (money)
Vendor identity (canonical sanity):  CLOSING = OPENING + RECEIPT - SALES.
Verified on every non-zero row of KLM DERMA.pdf (17 product rows).

Why a dedicated positional parser (NOT generic / simple4):
  * There is a leading numeric **Code** column (x0 ~78-100) — simple4's "pop the last
    N numbers" logic and the generic reader both mis-bind it and slide columns.
  * The Product Description / Packing text is glyph-scrambled by the PDF text layer
    (e.g. 'CANROLFIN1 C5GREMA M' for 'CANROLFIN 15 GM CREAM') AND the Packing sub-column
    prints stray digits ('10 0 GM', '130 1 0', '5 0 GM') that live in x ~150-220 — i.e.
    to the LEFT of the Opening column. A flat-text reader slurps those pack digits into
    the quantity columns and the reconcile collapses (100% false SANITY_FAILED under the
    generic layout).
  * There are TWO money columns (Sales Value + Stock Value) so the last-four heuristic
    reads Sales Value into closing.

The six quantity/value columns are RIGHT-aligned; the printed data right-edges (x1)
cluster very tightly and are ~51pt apart:
    Opening 255.2 | Receipt 306.8 | Sales 358.5 | Closing 410.0 | SalesVal 461.7 | StockVal 513.2
We read the header row's token x1 values as per-column right anchors and bucket every
numeric token whose x1 > NAME_CUT into the nearest column (within _TOL). Tokens with
x1 <= NAME_CUT are Code / product name / packing text and are never bucketed as values.
The Code (x0 < ~101) is dropped from the name; the remaining description/pack tokens
form the (scrambled but stable) product identity string.

Detect gate (compact, spaces-stripped, lowercased header run):
    'closingsalesvaluestockvalue'
This contiguous run — Closing then BOTH Sales Value and Stock Value — is unique to this
export. The KLM LAB sibling
(r15_klm_lab_open_recv_sales_close_value_positional) ends '...closingstockvalue'
(only one value column, no 'salesvalue' between), so it cannot collide. Place BEFORE the
coarse 'stock statement'+'product' -> simple4 fallback.
"""
import io
import re

# Data-value right-edge anchors (x1) read from the header; a numeric token binds to the
# column whose right edge it is nearest, within this window. Columns are ~51pt apart and
# printed numbers right-align a few points RIGHT of their header token, so a ~26pt window
# binds each number to the correct column without reaching a neighbour.
_TOL = 26.0

_HDR_ORDER = ("OPENING", "RECEIPT", "SALES", "CLOSING")

# x0 below this is the leading numeric Code column (drop from the product name).
_CODE_CUT = 102.0


def _to_f(t):
    t = t.replace(",", "")
    try:
        return float(t)
    except ValueError:
        return 0.0


def _is_num(t):
    t = t.replace(",", "")
    if not t:
        return False
    try:
        float(t)
        return True
    except ValueError:
        return False


def _header_anchors(row_words):
    """If this word row is the column header, return the ordered per-column right
    anchors (x1) for OPENING/RECEIPT/SALES/CLOSING + the two money columns, plus the
    OPENING x0 (the name/number boundary). Else None.

    The header prints 'Sales' twice (the SALES qty column and the 'Sales Value' money
    column) and 'Value' twice ('Sales Value', 'Stock Value'), so we resolve columns by
    x position rather than by unique text."""
    ups = [(w["text"].upper(), w) for w in row_words]
    names = {t for t, _ in ups}
    if not all(t in names for t in _HDR_ORDER):
        return None
    if "VALUE" not in names or "STOCK" not in names:
        return None

    # first (leftmost) OPENING / RECEIPT / CLOSING tokens
    def first(tok):
        cand = [w for t, w in ups if t == tok]
        return min(cand, key=lambda w: w["x0"]) if cand else None

    op = first("OPENING")
    rec = first("RECEIPT")
    cls = first("CLOSING")
    if not (op and rec and cls):
        return None
    # SALES qty = the SALES token left of CLOSING; 'Sales Value' SALES is right of it.
    sales_toks = sorted((w for t, w in ups if t == "SALES"), key=lambda w: w["x0"])
    sal = next((w for w in sales_toks if w["x0"] < cls["x0"]), None)
    if sal is None:
        return None
    # Sales Value right edge = the 'Value' token of the pair whose left neighbour is the
    # second 'Sales'; Stock Value right edge = the 'Value' token after 'Stock'.
    value_toks = sorted((w for t, w in ups if t == "VALUE"), key=lambda w: w["x0"])
    stock_tok = first("STOCK")
    if len(value_toks) < 2 or stock_tok is None:
        return None
    stock_val = min(value_toks, key=lambda w: abs(w["x0"] - stock_tok["x1"]))
    sales_val = next((w for w in value_toks if w is not stock_val), None)
    if sales_val is None:
        return None

    anchors = [
        ("OPENING", op["x1"]),
        ("RECEIPT", rec["x1"]),
        ("SALES", sal["x1"]),
        ("CLOSING", cls["x1"]),
        ("SALES_VALUE", sales_val["x1"]),
        ("STOCK_VALUE", stock_val["x1"]),
    ]
    # name/number boundary: a touch left of the OPENING column's left edge.
    name_cut = op["x0"] - 12.0
    return anchors, name_cut


def parse_r15_klm_pharmaasia_code_open_recv_sales_close_dualvalue(text, file_bytes=None):
    if not file_bytes:
        return []
    import pdfplumber

    records = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        anchors = None       # persists across pages once the header is seen
        name_cut = None

        for page in pdf.pages:
            words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
            by_top = {}
            for w in words:
                by_top.setdefault(round(w["top"]), []).append(w)

            for top in sorted(by_top):
                row_words = sorted(by_top[top], key=lambda w: w["x0"])
                joined = " ".join(w["text"] for w in row_words).strip()
                low = joined.lower()

                hdr = _header_anchors(row_words)
                if hdr:
                    anchors, name_cut = hdr
                    continue
                if anchors is None:
                    continue

                # banners / section-band / grand-total (no product, or value-only)
                if low.startswith("pharma asia") or low.startswith("stock statement"):
                    continue
                if low.startswith("klm ") and "(" in low:
                    # 'KLM ( DERMA ) Jun-26' division band — no product numbers
                    continue

                # name tokens = everything left of name_cut, minus the leading Code
                name_tokens = [w for w in row_words
                               if w["x1"] <= name_cut and w["x0"] >= _CODE_CUT]
                col_tokens = [w for w in row_words if w["x1"] > name_cut]
                name_str = " ".join(w["text"] for w in name_tokens).strip()

                if not name_str or not re.search(r"[A-Za-z]", name_str):
                    continue

                vals = {}
                for w in col_tokens:
                    t = w["text"]
                    if not _is_num(t):
                        continue
                    x1 = w["x1"]
                    best, bestd = None, _TOL
                    for cname, ax in anchors:
                        d = abs(x1 - ax)
                        if d < bestd:
                            bestd, best = d, cname
                    if best is None:
                        continue
                    vals.setdefault(best, _to_f(t))

                op = vals.get("OPENING", 0.0)
                rec = vals.get("RECEIPT", 0.0)
                sal = vals.get("SALES", 0.0)
                cls = vals.get("CLOSING", 0.0)
                sval = vals.get("SALES_VALUE", 0.0)
                stkval = vals.get("STOCK_VALUE", 0.0)

                name = re.sub(r"\s+", " ", name_str).strip()
                if len(name) < 2:
                    continue

                records.append({
                    "product_name": name,
                    "opening_stock": op,
                    "purchase_stock": rec,
                    "sales_qty": sal,
                    "closing_stock": cls,
                    "sales_value": sval,
                    "closing_stock_value": stkval,
                })

    return records
