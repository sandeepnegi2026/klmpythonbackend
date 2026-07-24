"""DAHOD PHARMAKON 'Stock and Sale Statement' — single-page glyph-interleaved KLM.

Header (one row):
  Item  Mar 26  Apr 26  OpStk  P.Qty  P.Val  P.Sch  S.Qty  S.Sch  S.Val  CrQty  ClStk  ClVal  Order

The text layer interleaves the item CODE with the product-name characters (e.g.
"1C0O94S4M2OQ CONDITIONER" = code 1094452 woven into "COSMOQ CONDITIONER"), and the
numeric cells are RIGHT-aligned with blank interiors, so a flat token parse cannot
align columns. We reuse marg_opstk_statement's glyph descrambler (_extract_clean_words_
from_pdf) to recover clean words with x-positions, then bucket each number into its
column by matching the number's RIGHT edge (x1) to the header label's right edge — the
same technique used by pharmassist_stock_sale_single.

Reconcile (verified on the printed column-total row 16 27 75 17 7371 2 20 3 9695 3 74
36052 8): ClStk = OpStk + P.Qty + P.Sch + CrQty - S.Qty - S.Sch  (75+17+2+3-20-3=74).
Mar/Apr are previous-month sales (ignored). P.Sch/CrQty fold into purchase_free and
S.Sch into sales_free, so closing = opening + purchase_stock + purchase_free -
sales_qty - sales_free. P.Val/S.Val/ClVal are the purchase/sale/closing rupee values.
"""
import re

_NUM_RE = re.compile(r"-?[\d,]*\d\.?\d*\.?$")  # allows trailing '.' (e.g. "15.") and commas

# printed header token -> internal column key (label right-edge is the bucket anchor)
_COL_MAP = {
    "OpStk": "Op", "P.Qty": "PQ", "P.Val": "PVal", "P.Sch": "PSch",
    "S.Qty": "SQ", "S.Sch": "SSch", "S.Val": "SVal", "CrQty": "Cr",
    "ClStk": "Cl", "ClVal": "ClVal", "Order": "Order",
}
_REQUIRED = ("Op", "PQ", "SQ", "Cl")

_INFLOW = ("PSch", "Cr")   # secondary inflows -> purchase_free
_OUTFLOW = ("SSch",)       # secondary outflows -> sales_free

_SKIP = ("klm", "total", "for ", "opening", "closing", "sales :", "note",
         "printed", "report", "page ", "stock and sale")


def _is_num(t):
    s = t.replace(",", "").rstrip(".")
    return bool(s) and _NUM_RE.fullmatch(t.replace(",", "")) and any(c.isdigit() for c in t)


def _to_f(t):
    try:
        return float(t.replace(",", "").rstrip("."))
    except ValueError:
        return 0.0


def _cluster_rows(words, tol=4):
    by_top = {}
    for w in words:
        by_top.setdefault(round(w["top"], 1), []).append(w)
    rows, cur, start = [], [], None
    for top in sorted(by_top):
        if start is None or top - start <= tol:
            if start is None:
                start = top
            cur.extend(by_top[top])
        else:
            rows.append(cur)
            cur, start = list(by_top[top]), top
    if cur:
        rows.append(cur)
    return rows


def _header_anchors(row):
    """Return {col: label right-edge x1} + name/number split boundary, or None."""
    right, first_x = {}, 1e9
    for w in row:
        if w["text"] in _COL_MAP:
            right[_COL_MAP[w["text"]]] = w["x1"]
        if w["text"] == "OpStk":
            first_x = min(first_x, w["x0"])
    if not all(k in right for k in _REQUIRED):
        return None
    # numbers (incl. the ignored Mar/Apr prior cols) start well left of OpStk; the name
    # ends before them. Use a fixed cut a bit left of the first data column.
    return {"right": right, "num_min": min(first_x - 90, 120)}


def _bucket(nums, right_edges):
    cols = list(right_edges.items())
    col = {}
    for w in nums:
        placed = min(cols, key=lambda kv: abs(kv[1] - w["x1"]))[0]
        col[placed] = _to_f(w["text"])
    return col


def parse_dahod_stock_sale_stmt(text, file_bytes=None):
    if not file_bytes:
        return []
    from extractors.stock_pdf.layouts.marg_opstk_statement import (
        _extract_clean_words_from_pdf,
    )

    words = _extract_clean_words_from_pdf(file_bytes)
    by_page = {}
    for w in words:
        by_page.setdefault(w.get("page", 0), []).append(w)

    records = []
    anchors = None
    for page in sorted(by_page):
        for row in _cluster_rows(by_page[page]):
            row = sorted(row, key=lambda w: w["x0"])
            found = _header_anchors(row)
            if found:
                anchors = found
                continue
            if not anchors:
                continue

            num_min = anchors["num_min"]
            low_line = " ".join(w["text"] for w in row).strip().lower()
            if any(low_line.startswith(p) for p in _SKIP):
                continue

            nums = [w for w in row if w["x0"] >= num_min and _is_num(w["text"])]
            name_toks = [w["text"] for w in row if w["x0"] < num_min]
            name = " ".join(name_toks).strip()
            if not name or not nums:
                continue

            col = _bucket(nums, anchors["right"])
            op = col.get("Op", 0.0)
            pq = col.get("PQ", 0.0)
            sq = col.get("SQ", 0.0)
            cl = col.get("Cl", 0.0)
            pf = sum(col.get(c, 0.0) for c in _INFLOW)
            sf = sum(col.get(c, 0.0) for c in _OUTFLOW)

            if op == 0 and pq == 0 and sq == 0 and cl == 0 and pf == 0 and sf == 0:
                continue

            records.append({
                "product_name": name,
                "opening_stock": op,
                "purchase_stock": pq,
                "purchase_free": pf,
                "sales_qty": sq,
                "sales_free": sf,
                "closing_stock": cl,
                "purchase_value": col.get("PVal", 0.0),
                "sales_value": col.get("SVal", 0.0),
                "closing_stock_value": col.get("ClVal", 0.0),
                "order_qty": col.get("Order", 0.0),
            })
    return records
