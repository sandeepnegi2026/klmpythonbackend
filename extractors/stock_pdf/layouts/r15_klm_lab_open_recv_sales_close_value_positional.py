"""LAXMI DISTRIBUTORS 'Stock Statement' — KLM LAB 5-column positional export.

Vendor:  LAXMI DISTRIBUTORS (KLM LABORATORIES divisions; one section per division
         inside a single multi-page PDF: 'KLM LAB- COSMOCOR DIV', 'KLM LAB-COSMO
         DIV.', 'KLM LAB-DERMA DIV.', 'KLM LAB-PEDIA DIV', ...).

Header (printed once per division section):

    Product Description   Packing   Opening   Receipt   Sales   Closing   Stock Value

Five numeric columns after Packing:
    Opening      -> opening_stock
    Receipt      -> purchase_stock
    Sales        -> sales_qty
    Closing      -> closing_stock
    Stock Value  -> closing_stock_value
Vendor identity (canonical sanity):  CLOSING = OPENING + RECEIPT - SALES.

Why positional (NOT simple4): zero cells are printed as a bare '0' in the Stock
Value column ONLY (the four quantity cells are simply BLANK), and any quantity cell
that is zero is also left blank. pdfplumber's flat text extraction collapses those
blanks, so the number of tokens per line varies (1, 3, 4 or 5) and their meaning is
positional, not order-based. The coarse 'stock statement'+'product' -> simple4
fallback pops the LAST four numbers as opening/receipt/sales/closing, which for any
row with a blank Receipt (e.g. 'MELBOOST TAB   30 22 8 1281.34') slides every column
one slot right and slurps the Stock Value (1281.34) into closing_stock -> ~70% false
SANITY_FAILED. simple4 operates on text lines only and cannot recover the blanks, so
a dedicated x-coordinate parser is required.

The five quantity/value columns are RIGHT-aligned; each printed number's right edge
(x1) sits at its column's right edge. We read the header row's token x1 values as the
per-column right anchors and bucket every numeric token into the nearest column whose
right anchor it is closest to (within a tolerance), so a blank column simply receives
no token. Product-name / pack text (and any pack digits like '625', '10') live left
of the Opening column's left edge (name_cut) and are never bucketed.

Skipped as non-product: the 'Totals' grand-total row (Stock Value only), the repeated
'Product Description ... Stock Value' header, the 'LAXMI DISTRIBUTORS' / 'Stock
Statement Print Date' banners, and the 'KLM LAB- <DIV>' division-band lines (which
carry no numbers). A running division label is captured from those band lines.

reconcile on LAXMI 'KLM LAB- ALL DIV -May2026..pdf' (COSMOCOR section):
    EPISERT CREAM 30 GM   op20 recv30 sales22 -> close28  (20+30-22=28) OK
    MELBOOST TAB          op0  recv30 sales22 -> close8   (0+30-22=8)  OK
    NIOSOL OINTMENT       op9  recv200 sales206-> close3  (9+200-206=3) OK
    RESOTEN 20 MG CAP     op7  recv30 sales11 -> close26  (7+30-11=26) OK
every non-zero row balances; blank/zero rows carry no numbers.

Detect: gate on the compact header run 'openingreceiptsalesclosingstockvalue' — a
contiguous 5-column header unique to this KLM LAB export (the klm_lmsale sibling reads
'openingreceiptstotalsalesclosing...', i.e. 'receiptstotal' not 'receiptsales', so it
cannot collide). It MUST be placed before the coarse 'stock statement'+'product' ->
simple4 fallback.
"""
import io
import re

# column right-anchor tolerance (points): a number is assigned to the column whose
# right edge (x1) is nearest, provided within this window. Printed numbers are
# right-aligned a few points to the RIGHT of their header token's right edge, and
# adjacent columns are ~51pt apart, so a ~24pt window binds each number to the correct
# column without ever reaching the neighbouring column's anchor.
_TOL = 24.0

_HDR_ORDER = ("OPENING", "RECEIPT", "SALES", "CLOSING")


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
    """If this word row is the column header, return column right-anchors (x1)
    for OPENING/RECEIPT/SALES/CLOSING plus the Stock-Value right anchor, else None."""
    by_text = {}
    for w in row_words:
        by_text.setdefault(w["text"].upper(), w)
    if not all(t in by_text for t in _HDR_ORDER):
        return None
    if "VALUE" not in by_text and "STOCK" not in by_text:
        return None
    anchors = [(t, by_text[t]["x1"]) for t in _HDR_ORDER]
    # Stock Value right anchor: rightmost of 'STOCK'/'VALUE' tokens
    val_x1 = None
    for k in ("VALUE", "STOCK"):
        if k in by_text:
            val_x1 = max(val_x1 or 0.0, by_text[k]["x1"])
    if val_x1 is not None:
        anchors.append(("VALUE", val_x1))
    return anchors


_DIV_RE = re.compile(r"KLM\s+LAB[-\s]+(.+?)\s+DIV", re.I)


def parse_r15_klm_lab_open_recv_sales_close_value_positional(text, file_bytes=None):
    if not file_bytes:
        return []
    import pdfplumber

    records = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        anchors = None       # [(col, x1), ...] once header seen; persists across pages
        name_cut = None      # left edge of the OPENING column
        division = ""

        for page in pdf.pages:
            words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
            by_top = {}
            for w in words:
                by_top.setdefault(round(w["top"]), []).append(w)

            for top in sorted(by_top):
                row_words = sorted(by_top[top], key=lambda w: w["x0"])
                joined = " ".join(w["text"] for w in row_words).strip()
                low = joined.lower()

                # (re)acquire header anchors whenever a header row is seen (per section)
                found = _header_anchors(row_words)
                if found:
                    anchors = found
                    # OPENING column left edge = its x1 minus a nominal width; use the
                    # header OPENING token x0 for a firm name/number boundary.
                    op_word = next(w for w in row_words
                                   if w["text"].upper() == "OPENING")
                    name_cut = op_word["x0"] - 8.0
                    continue

                if anchors is None:
                    # capture division band before the first header, too
                    m = _DIV_RE.search(joined)
                    if m:
                        division = re.sub(r"\s+", " ", m.group(1)).strip().rstrip(".")
                    continue

                # division band line (carries no product numbers)
                m = _DIV_RE.search(joined)
                if m:
                    division = re.sub(r"\s+", " ", m.group(1)).strip().rstrip(".")
                    continue

                # banners / totals
                if low.startswith("laxmi") or low.startswith("stock statement"):
                    continue
                if low.startswith("total"):
                    continue

                # split name text (left of name_cut) from numeric column tokens
                name_tokens = [w for w in row_words if w["x1"] <= name_cut]
                col_tokens = [w for w in row_words if w["x1"] > name_cut]
                name_str = " ".join(w["text"] for w in name_tokens).strip()

                if not name_str or not re.search(r"[A-Za-z]", name_str):
                    continue

                # bucket each numeric column token into nearest right-anchor
                vals = {}
                for w in col_tokens:
                    t = w["text"]
                    if not _is_num(t):
                        continue
                    x1 = w["x1"]
                    best = None
                    bestd = _TOL
                    for cname, ax in anchors:
                        d = abs(x1 - ax)
                        if d < bestd:
                            bestd = d
                            best = cname
                    if best is None:
                        continue
                    vals.setdefault(best, _to_f(t))

                op = vals.get("OPENING", 0.0)
                rec = vals.get("RECEIPT", 0.0)
                sal = vals.get("SALES", 0.0)
                cls = vals.get("CLOSING", 0.0)
                val = vals.get("VALUE", 0.0)

                name = re.sub(r"\s+", " ", name_str).strip()
                if len(name) < 2:
                    continue

                rec_row = {
                    "product_name": name,
                    "opening_stock": op,
                    "purchase_stock": rec,
                    "sales_qty": sal,
                    "closing_stock": cls,
                    "closing_stock_value": val,
                }
                if division:
                    rec_row["division"] = division
                records.append(rec_row)

    return records
