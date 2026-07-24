"""NAVKAR APOTEK LLP (SHREE AGENCIES) 'Stock sales statement' — KLM two-page
split positional export.

Vendor:  NAVKAR APOTEK LLP / SHREE AGENCIES, per KLM LABORATORIES division band
         ('KLM LABORATORIES PED', 'KLM LABORATORIES PHARMA').

The report is printed WIDE and split across two physical pages: page 0 carries the
LEFT half of the columns, page 1 the RIGHT half, and each product row occupies the
SAME vertical position (``top``) on both pages. The two header halves are:

    PAGE 0:  Product Name | Pack | Rate | Prev.Last | Prev.Sal | Opening | Purchase | P.Free
    PAGE 1:  Tot.Purchase | Sales | P.Repl | S.Free | SValue | S.Repl | Adj/P.Rtn | Closing | P.Rtn.Free | Cl.Value

Column -> canonical mapping (qty and value kept strictly separate):
    Opening    (p0) -> opening_stock
    Purchase   (p0) -> purchase_stock
    P.Free     (p0) -> purchase_free
    Rate       (p0) -> rate
    Sales      (p1) -> sales_qty
    S.Free     (p1) -> sales_free
    Adj/P.Rtn  (p1) -> sales_return   (signed stock adjustment; folded into the +sr
                                       slot so the vendor's own closing identity holds)
    Closing    (p1) -> closing_stock
    Cl.Value   (p1) -> closing_stock_value
    Prev.Last / Prev.Sal / Tot.Purchase / SValue -> informational (no canonical home)
    P.Repl / S.Repl / P.Rtn.Free -> replacement/return-free columns; blank on this
        export (all rows). Read positionally but zero here, so they do not disturb
        the reconcile.

Vendor identity (canonical sanity), verified on all 28 product rows of the reference
file (NAVKAR 'Stock sales statement 01-05-2026 - 31-05-2026KLMPDF.pdf'):
    closing = opening + purchase + P.Free - Sales - S.Free + (Adj/P.Rtn signed)
    e.g. SACCTIK GG SACHET: 400 + 500 + 0 - 253 - 50 + (-87) = 510  OK
         SOFIBAR SYNDET BAR: 173 + 301 + 37 - 283 - 28 + 2       = 202  OK
         MUPISOFT OINT 5GM:   32 +  76 +  3 -  36 -  4 + 0        =  71  OK
    every row reconciles exactly.

Why positional (NOT any text-flow parser): because the columns live on two separate
pages, no single text line ever carries a product's full number set. The current
routing to ``marg_stock_long`` (coarse 'opening'+'sale'+'repl' rule) sees only the
page-0 tail (Opening/Purchase/P.Free) and mis-maps it -> 100% false SANITY_FAILED.
Reading requires (a) x-coordinate column binding — interior cells (Prev.Last,
Prev.Sal, S.Free, Adj/P.Rtn, ...) blank out for no-movement rows, so the flat text
token index shifts row to row — and (b) correlating the two pages by ``top``.

The five/ten numeric columns are RIGHT-aligned to their header token's right edge
(x1); we read each page's header row's token x1 values as per-column right anchors and
bucket every numeric token into the nearest anchor within a tolerance, so a blank
column simply receives no token.

Detect: gate on the compact page-0 header run
    'prev.lastprev.salopeningpurchasep.free'
which is unique to this export ('prev.last' appears in no other stock_pdf layout).
It MUST be placed before the coarse 'opening'+'sale'+'repl' -> marg_stock_long rule.
"""
import io
import re

# right-anchor tolerance (points): a number is bound to the column whose header
# right edge (x1) is nearest, within this window. Adjacent columns are ~40-50pt
# apart and printed numbers sit within a few points of their header x1, so a ~22pt
# window binds each number without reaching a neighbouring anchor.
_TOL = 22.0

# page-0 header tokens whose right edge (x1) anchors the numeric columns
_P0_COLS = ("RATE", "PREV.LAST", "PREV.SAL", "OPENING", "PURCHASE", "P.FREE")
# page-1 header tokens (right edge anchors)
_P1_COLS = (
    "TOT.PURCHASE", "SALES", "P.REPL", "S.FREE", "SVALUE",
    "S.REPL", "ADJ/P.RTN", "CLOSING", "P.RTN.FREE", "CL.VALUE",
)


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


def _rows_by_top(page):
    words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
    by_top = {}
    for w in words:
        by_top.setdefault(round(w["top"]), []).append(w)
    for top in by_top:
        by_top[top] = sorted(by_top[top], key=lambda w: w["x0"])
    return by_top


def _header_anchors(row_words, wanted):
    """If this row is the column header, return {COL: right-anchor x1}, else None."""
    by_text = {w["text"].upper(): w for w in row_words}
    if not all(c in by_text for c in wanted):
        return None
    return {c: by_text[c]["x1"] for c in wanted}


def _bucket(row_words, anchors, name_cut):
    """Bucket numeric tokens whose x1 is right of name_cut into nearest anchor."""
    vals = {}
    for w in row_words:
        t = w["text"]
        if name_cut is not None and w["x1"] <= name_cut:
            continue
        if not _is_num(t):
            continue
        x1 = w["x1"]
        best, bestd = None, _TOL
        for col, ax in anchors.items():
            d = abs(x1 - ax)
            if d < bestd:
                bestd, best = d, col
        if best is not None:
            vals.setdefault(best, _to_f(t))
    return vals


def parse_r15_klm_ss_prevlast_twopage_positional(text, file_bytes=None):
    if not file_bytes:
        return []
    import pdfplumber

    records = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        p0_anchors = None
        p1_anchors = None
        name_cut = None            # left edge of the Opening column on page 0
        # gather page-0 product rows keyed by top: {top: (name, {p0 vals}, division)}
        p0_rows = {}
        # gather page-1 rows keyed by top: {top: {p1 vals}}
        p1_rows = {}

        for page in pdf.pages:
            by_top = _rows_by_top(page)

            # locate this page's header (page 0 vs page 1 have disjoint token sets)
            page_kind = None
            hdr_top = None
            for top in sorted(by_top):
                a0 = _header_anchors(by_top[top], _P0_COLS)
                if a0:
                    p0_anchors = a0
                    rate_word = next(w for w in by_top[top]
                                     if w["text"].upper() == "RATE")
                    name_cut = rate_word["x0"] - 8.0
                    page_kind = "p0"
                    hdr_top = top
                    break
                a1 = _header_anchors(by_top[top], _P1_COLS)
                if a1:
                    p1_anchors = a1
                    page_kind = "p1"
                    hdr_top = top
                    break

            if page_kind == "p0" and p0_anchors:
                division = ""
                for top in sorted(by_top):
                    if top <= hdr_top:          # skip title/city banners above the header
                        continue
                    row = by_top[top]
                    joined = " ".join(w["text"] for w in row).strip()
                    low = joined.lower()
                    # header row itself
                    if _header_anchors(row, _P0_COLS):
                        continue
                    # banners / footers
                    if (low.startswith("total") or low.startswith("grand total")
                            or low.startswith("bill nos") or low.startswith("stock sales")
                            or low.startswith("navkar") or low.startswith("shree")):
                        continue
                    # division band: 'KLM LABORATORIES PED', all letters, no numbers
                    name_tokens = [w for w in row if name_cut is None or w["x1"] <= name_cut]
                    num_tokens = [w for w in row
                                  if (name_cut is not None and w["x1"] > name_cut)
                                  and _is_num(w["text"])]
                    name_str = " ".join(w["text"] for w in name_tokens).strip()
                    if not name_str or not re.search(r"[A-Za-z]", name_str):
                        continue
                    if "laboratories" in low and not num_tokens:
                        division = re.sub(r"\s+", " ", joined).strip()
                        continue
                    vals = _bucket(row, p0_anchors, name_cut)
                    p0_rows[top] = (re.sub(r"\s+", " ", name_str).strip(), vals, division)

            elif page_kind == "p1" and p1_anchors:
                for top in sorted(by_top):
                    if top <= hdr_top:
                        continue
                    row = by_top[top]
                    vals = _bucket(row, p1_anchors, None)
                    if vals:
                        p1_rows[top] = vals

        # correlate page-0 rows with page-1 rows by nearest top (within a few pt)
        p1_tops = sorted(p1_rows)
        for top in sorted(p0_rows):
            name, v0, division = p0_rows[top]
            v1 = p1_rows.get(top, {})
            if not v1 and p1_tops:
                # tolerate 1-2pt vertical drift between the two pages
                near = min(p1_tops, key=lambda t: abs(t - top))
                if abs(near - top) <= 2:
                    v1 = p1_rows.get(near, {})

            rec = {
                "product_name": name,
                "rate": v0.get("RATE", 0.0),
                "opening_stock": v0.get("OPENING", 0.0),
                "purchase_stock": v0.get("PURCHASE", 0.0),
                "purchase_free": v0.get("P.FREE", 0.0),
                "sales_qty": v1.get("SALES", 0.0),
                "sales_free": v1.get("S.FREE", 0.0),
                "sales_return": v1.get("ADJ/P.RTN", 0.0),
                "closing_stock": v1.get("CLOSING", 0.0),
                "closing_stock_value": v1.get("CL.VALUE", 0.0),
            }
            if division:
                rec["division"] = division
            records.append(rec)

    return records
