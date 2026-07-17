"""AAGAM/MARUTI/VISNAGAR (pharmabyte / Sky Way ERP) "Stock and Sale Statement" —
SINGLE-page glyph-interleaved StkAd variant of the DAHOD/Venus family.

Header (one row; the two prev-month columns and StkAd are optional per file):
  Item [Apr 26] [May 26] OpStk P.Qty P.Val P.Sch S.Qty S.Sch S.Val [StkAd] ClStk ClVal [Order]

Three sibling headers land here (all share the doubled scheme run P.Sch/S.Qty/S.Sch/S.Val
and carry NO CrQty column — the CrQty presence is what routes the DAHOD/Venus siblings):
  AAGAM    : Apr 26 May 26 OpStk P.Qty P.Val P.Sch S.Qty S.Sch S.Val StkAd ClStk ClVal
  VISNAGAR : OpStk P.Qty P.Val P.Sch S.Qty S.Sch S.Val ClStk ClVal Order
  MARUTI   : OpStk P.Qty P.Val P.Sch S.Qty S.Sch S.Val ClStk ClVal

Like DAHOD, the text layer interleaves the item CODE with the product-name characters
(e.g. "I0M2E2L4B4OOST TABLET" = code 0224484 woven into "MELBOOST TABLET") and every
numeric cell is RIGHT-aligned with blank interiors, so a flat token parse cannot align
columns. We reuse marg_opstk_statement's glyph descrambler (_extract_clean_words_from_pdf)
to recover clean words with x-positions, then bucket each number into its column by
matching the number's RIGHT edge (x1) to the header label's right edge — the same
technique used by dahod_stock_sale_stmt / pharmassist_stock_sale_single.

The two prev-month columns (Apr/May) sit LEFT of OpStk; they are previous-month SALES
qty and must be ignored. Their "26" year token gives a right-edge anchor, so we add
AprPrev/MayPrev SINK columns and route prev-month numbers there (dropped) rather than
letting them collide onto OpStk.

Reconcile (verified on the printed division-total rows, e.g. AAGAM COSMOCOR total
553 194 25131 16 155 9 23577 0 599 89623 and a StkAd=-9 total 221 185 297 152 15462 11
147 12 18661 -9 292 35851):
    ClStk = OpStk + P.Qty + P.Sch - S.Qty - S.Sch + StkAd
P.Sch folds into purchase_free (inflow), S.Sch into sales_free (outflow), and StkAd is a
SIGNED stock adjustment that ADDS to closing, so it maps to sales_return (the +sr slot;
a negative StkAd correctly subtracts). P.Val/S.Val/ClVal are the rupee value columns.
"""
import re

from extractors.stock_pdf.layouts.marg_opstk_statement import (
    _decode_pharmabyte,
    _extract_clean_words_from_pdf,
    _looks_pharmabyte,
)
from extractors.stock_pdf.parse_common import _split_product_pack

_NUM_RE = re.compile(r"-?[\d,]*\d\.?\d*\.?$")  # allows trailing '.' and commas, optional sign

# printed header token -> internal column key (label right-edge x1 is the bucket anchor).
# AprPrev/MayPrev are SINK buckets for the ignored prev-month columns.
_COL_MAP = {
    "OpStk": "Op", "P.Qty": "PQ", "P.Val": "PVal", "P.Sch": "PSch",
    "S.Qty": "SQ", "S.Sch": "SSch", "S.Val": "SVal", "DbQty": "DbQty",
    "StkAd": "StkAd", "ClStk": "Cl", "ClVal": "ClVal", "Order": "Order",
}
_REQUIRED = ("Op", "PQ", "SQ", "Cl")

# NOTE: 'klm' is deliberately NOT in _SKIP — this vendor sells genuine KLM-brand
# products (KLM-C 20 SERUM, KLMITE CREAM/SOAP). The division band is caught separately
# by the "^KLM ... DIVISION" test below, so KLM- products survive.
_SKIP = ("total", "for ", "opening", "closing", "sales :", "note",
         "printed", "report", "page ", "stock and sale", "item")


def _is_num(t):
    s = t.replace(",", "")
    return bool(_NUM_RE.fullmatch(s)) and any(c.isdigit() for c in t)


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
    """Return {col: label right-edge x1} incl. prev-month sinks + name/number cut, or None."""
    right, opstk_x0 = {}, 1e9
    year_edges = []
    for w in row:
        if w["text"] in _COL_MAP:
            right[_COL_MAP[w["text"]]] = w["x1"]
        if w["text"] == "OpStk":
            opstk_x0 = min(opstk_x0, w["x0"])
        # prev-month year tokens ("26") sit between Item and OpStk
        if w["text"].strip() in ("26", "25", "27") and w["x0"] < 205:
            year_edges.append(w["x1"])
    if not all(k in right for k in _REQUIRED):
        return None
    # add sink buckets for the (up to two) ignored prev-month columns
    for i, ed in enumerate(sorted(year_edges)[:2]):
        right[f"Prev{i}"] = ed
    # the product name ends before the first data column; cut a little left of OpStk
    num_min = min(opstk_x0 - 45, 120) if opstk_x0 < 1e9 else 120
    return {"right": right, "num_min": num_min}


def _bucket(nums, right_edges):
    cols = list(right_edges.items())
    col = {}
    # place each number on the header whose right-edge is nearest; process left-to-right
    # so if two numbers collide on one column the rightmost (real) value wins.
    for w in sorted(nums, key=lambda w: w["x0"]):
        placed = min(cols, key=lambda kv: abs(kv[1] - w["x1"]))[0]
        col[placed] = _to_f(w["text"])
    return col


def parse_stock_sale_stmt_stkad(text, file_bytes=None):
    if not file_bytes:
        return []

    words = _extract_clean_words_from_pdf(file_bytes)
    if not words:
        return []

    is_pharmabyte = _looks_pharmabyte(
        " ".join(w["text"] for w in words[:200])
    )

    by_page = {}
    for w in words:
        by_page.setdefault(w.get("page", 0), []).append(w)

    records = []
    division = ""
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
            line = " ".join(w["text"] for w in row).strip()
            low_line = line.lower()
            # division band, e.g. "KLM - COSMOCOR DIVISION" / "KLM LAB. DIVISION". Gated on
            # DIVISION so genuine KLM-brand products (KLM-C 20 SERUM, KLMITE CREAM) survive.
            if re.match(r"^klm\b", line, re.I) and (
                "DIVISION" in line.upper() or "DIVISON" in line.upper()
            ):
                division = line
                continue
            if any(low_line.startswith(p) for p in _SKIP):
                continue
            if "DIVISION" in line.upper() or "DIVISON" in line.upper():
                continue

            nums = [w for w in row if w["x0"] >= num_min and _is_num(w["text"])]
            name_toks = [w["text"] for w in row if w["x0"] < num_min]
            name = " ".join(name_toks).strip()
            # strip embedded file-id tokens (VS1234 / MF070) some exports print in the name
            name = re.sub(r"V[SI]\d{4}", " ", name)
            name = re.sub(r"MF\d{3}", " ", name)
            name = re.sub(r"\s+", " ", name).strip()
            if not name or not nums:
                continue

            name, pack = _split_product_pack(name)
            name = re.sub(r"^[A-Z]{1,2}\d{3,5}\s*", "", name).strip()
            if is_pharmabyte:
                parts = name.split()
                if parts:
                    dec = _decode_pharmabyte(parts[0])
                    if dec != parts[0]:
                        parts[0] = dec
                    name = " ".join(parts)
            if not name or len(name) < 3 or "*" in name:
                continue
            if "DIVISION" in name.upper() or "DIVISON" in name.upper():
                continue

            col = _bucket(nums, anchors["right"])
            op = col.get("Op", 0.0)
            pq = col.get("PQ", 0.0)
            sq = col.get("SQ", 0.0)
            cl = col.get("Cl", 0.0)
            pf = col.get("PSch", 0.0)   # purchase scheme/free (inflow)
            # sales scheme/free (S.Sch) and Debit Qty (DbQty) are both stock OUTFLOWS;
            # fold both into sales_free (the -sf slot). DbQty is absent in the cluster
            # files (AAGAM/VISNAGAR-MF070) and present in the GUJARAT VISNAGAR exports.
            sf = col.get("SSch", 0.0) + col.get("DbQty", 0.0)
            adj = col.get("StkAd", 0.0)  # signed stock adjustment (+ to stock)

            if op == 0 and pq == 0 and sq == 0 and cl == 0 and pf == 0 and sf == 0:
                continue

            rec = {
                "product_name": name,
                "pack": pack,
                "division": division,
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
            }
            # StkAd is a signed stock adjustment that ADDS to closing; map to the +sr
            # (sales_return) slot so the reconcile op+pur+pf-sal-sf+sr = closing holds
            # for both signs. Only set when present so no-StkAd files stay clean.
            if adj:
                rec["sales_return"] = adj
            records.append(rec)
    return records
