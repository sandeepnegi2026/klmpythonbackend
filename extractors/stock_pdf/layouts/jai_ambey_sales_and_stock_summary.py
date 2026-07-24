"""JAI AMBEY SALES "Sales And Stock (Summary)" stock report (KLM / PEDIA division).

Marg-style summary export. The page header block reprints the firm banner twice,
then a THREE-line grouped column header whose labels are split across baselines:

    (line A) In Stock   Out  Out Stock  Cl.Stock  As
    (line B) Product  OpStock  OpValue  In Stock ..............  Cl.Value
    (line C)          Value    Stock    Value    On

Read flat as text the header collapses, but the eight numeric columns are
LEFT-aligned to rock-stable x0 positions, so this is parsed POSITIONALLY: each
numeric word is bucketed to the nearest column anchor (anchors derived per file
from the header-label x0's, with hard-coded fallbacks). Product names frequently
WRAP onto a second (and the numbers land on the row BETWEEN or beside the name),
e.g.:

    SACCTIK GG ORAL
    10.00 2400.00 0.00 0.00 0.00 0.00 10.00 2400.00
    DROPS

so name fragments are accumulated across consecutive number-less rows and glued
to the single numeric row (a flat parser DROPPED these 3 wrapped rows entirely,
which is exactly the mis-map the audit flagged).

Eight numeric columns and their canonical mapping (money -> *_value, NOT qty):

    header col        meaning              canonical field
    ----------------- -------------------- --------------------
    OpStock           opening qty          opening_stock
    OpValue           opening money        opening_value
    In Stock          inflow qty           purchase_stock
    In Stock Value    inflow money         purchase_value
    Out Stock         sales/outflow qty    sales_qty
    Out Stock Value   sales money          sales_value
    Cl.Stock          closing qty          closing_stock
    Cl.Value          closing money        closing_stock_value

(The generic parser mis-mapped OpValue -> purchase_stock and Cl.Value ->
closing_stock, i.e. it slid money into qty fields; fixed here by anchor bucketing.)

Reconcile identity (holds on every row, verified against the printed Grand Total
and per row, e.g. KLM D3 NANO DROPS 20+0-14=6; SOFIKID 20+72-73=19):

    closing_stock == opening_stock + purchase_stock - sales_qty

which is exactly postprocess.sanity_warnings with purchase_free/return and
sales_free/return all 0. Grand Total footer row is skipped.
"""
import io
import re

import pdfplumber

# Column keys in left-to-right order, each paired with a fallback x0 anchor
# (measured on the KLM/PEDIA sample; the whole grid is stable within this vendor).
_COLUMNS = [
    ("opening_stock", 185.6),        # OpStock
    ("opening_value", 220.8),        # OpValue         (money)
    ("purchase_stock", 265.8),       # In Stock
    ("purchase_value", 299.7),       # In Stock Value  (money)
    ("sales_qty", 344.9),            # Out Stock
    ("sales_value", 378.8),          # Out Stock Value (money)
    ("closing_stock", 423.8),        # Cl.Stock
    ("closing_stock_value", 480.2),  # Cl.Value        (money)
]
# Header token -> which column its x0 pins. Only tokens that sit at a column's
# left edge are used; ambiguous repeated tokens (Stock/Value/Out) are resolved by
# left-to-right order against the fallback anchors below.
_ANCHOR_HEADER_TOKENS = ("OpStock", "OpValue", "In", "Out", "Cl.Stock", "Cl.Value")

_NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*")
_SKIP_PREFIXES = (
    "grand total", "product", "opstock", "opvalue", "in stock", "out stock",
    "cl.stock", "cl.value", "value", "stock", "as", "on",
    "jai ambey", "raj hospital", "road,", "dhanbad", "gstin", "(o)",
    "sales and stock", "(summary)", "(from", "20aarfj",
)


def _is_num(t):
    s = t.replace(",", "")
    return bool(re.fullmatch(r"-?\d+\.?\d*", s)) and any(c.isdigit() for c in s)


def _to_f(t):
    try:
        return float(t.replace(",", ""))
    except ValueError:
        return 0.0


def _word_rows(page):
    """Cluster a page's words into y-rows (tolerant of ~2px baseline wobble)."""
    words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
    by_top = {}
    for w in words:
        k = round(w["top"])
        matched = None
        for kk in by_top:
            if abs(kk - k) <= 2:
                matched = kk
                break
        by_top.setdefault(matched if matched is not None else k, []).append(w)
    return [sorted(by_top[t], key=lambda w: w["x0"]) for t in sorted(by_top)]


def _derive_anchors(rows):
    """Derive column x0 anchors from the header-label positions, else fallbacks.

    The header 'Product OpStock OpValue In Stock ... Cl.Value' line carries clean
    x0's for OpStock/OpValue/In/Cl.Value; the 'In Stock Out Out Stock Cl.Stock'
    line carries Out(x2)/Cl.Stock. We collect every anchor-token x0 seen anywhere
    in the header band and snap each of the eight fallback anchors to the nearest
    header x0 within 8pt, so a per-file horizontal shift is absorbed while the
    column ORDER stays fixed.
    """
    header_x0 = []
    for row in rows:
        toks = [w["text"] for w in row]
        low = " ".join(toks).lower()
        if "product" in low and "opstock" in low:
            for w in row:
                if w["text"] in _ANCHOR_HEADER_TOKENS:
                    header_x0.append(w["x0"])
        if low.startswith("in stock") and "cl.stock" in low:
            for w in row:
                if w["text"] in ("Out", "Cl.Stock"):
                    header_x0.append(w["x0"])
    anchors = []
    for _key, fb_x0 in _COLUMNS:
        best = fb_x0
        best_d = 8.0
        for hx in header_x0:
            d = abs(hx - fb_x0)
            if d < best_d:
                best_d = d
                best = hx
        anchors.append(best)
    return anchors


def _bucket(nums, anchors):
    """Assign each numeric word to the nearest column anchor by its x0."""
    col = {}
    for w in nums:
        idx = min(range(len(anchors)), key=lambda i: abs(anchors[i] - w["x0"]))
        col[_COLUMNS[idx][0]] = _to_f(w["text"])
    return col


def parse_jai_ambey_sales_and_stock_summary(text, file_bytes=None):
    if not file_bytes:
        return []

    records = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            rows = _word_rows(page)
            anchors = _derive_anchors(rows)
            pending_name = []  # name fragments seen BEFORE the numeric row
            tail_target = None  # record whose numeric row carried NO inline name
                                # -> the next pure-name row is its WRAPPED tail
            for row in rows:
                toks = [w["text"] for w in row]
                line_low = " ".join(toks).strip().lower()
                if not line_low:
                    continue
                if any(line_low.startswith(p) for p in _SKIP_PREFIXES):
                    pending_name = []
                    tail_target = None
                    continue

                nums = [w for w in row if _is_num(w["text"])]
                name_words = [w["text"] for w in row if not _is_num(w["text"])]

                if not nums:
                    # pure name fragment. If the previous numeric row had no inline
                    # name (name came only from the row ABOVE), this fragment is the
                    # bottom half of that wrapped name -> glue it there.
                    if tail_target is not None and name_words:
                        tail_target["product_name"] = (
                            tail_target["product_name"] + " " + " ".join(name_words)
                        ).strip()
                        tail_target = None
                    elif name_words:
                        pending_name.extend(name_words)
                    continue

                tail_target = None
                # numeric row: name = same-row leading text + any stashed fragments
                inline_name = bool(name_words)
                name = " ".join(pending_name + name_words).strip()
                pending_name = []
                if not name:
                    continue

                col = _bucket(nums, anchors)
                rec = {
                    "product_name": name,
                    "pack": "",
                    "opening_stock": col.get("opening_stock", 0.0),
                    "opening_value": col.get("opening_value", 0.0),
                    "purchase_stock": col.get("purchase_stock", 0.0),
                    "purchase_value": col.get("purchase_value", 0.0),
                    "sales_qty": col.get("sales_qty", 0.0),
                    "sales_value": col.get("sales_value", 0.0),
                    "closing_stock": col.get("closing_stock", 0.0),
                    "closing_stock_value": col.get("closing_stock_value", 0.0),
                }
                records.append(rec)
                # If this numeric row had NO inline name (name came purely from the
                # row above), the product name may WRAP onto the row below -> arm the
                # tail so the next pure-name fragment glues here. When the numeric row
                # already carried its own name, no wrapped tail can follow it.
                if not inline_name:
                    tail_target = rec

    return records
