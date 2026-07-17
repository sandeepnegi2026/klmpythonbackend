"""KHURANA 'STOCK & SALES ANALYSIS' — ITEM DESCRIPTION positional 4-column export.

Vendor:  KHURANA MEDICOS, KLM LABORATORIES divisions (one PDF per division;
         title 'STOCK & SALES ANALYSIS ( KLM PHARMA )').
Header (printed once):

    ITEM DESCRIPTION      OPENING   RECEIPT   ISSUE   CLOSING

There are only four quantity columns and NO value/free/return columns:
    OPENING  -> opening_stock
    RECEIPT  -> purchase_stock
    ISSUE    -> sales_qty
    CLOSING  -> closing_stock
so the vendor identity (and canonical sanity) is simply:
    CLOSING = OPENING + RECEIPT - ISSUE.

Why positional (not simple4): zero cells print as a bare '-' or are blank, and
BOTH the product name AND its four numbers frequently wrap onto a second physical
line (the number baseline splits into two 'top' bands). The flat-text simple4 rule
collapses those wraps — it drops ~6 rows (21 -> 14) and mis-binds the survivors,
tripping SANITY_FAILED. The four columns are left-aligned at fixed x-positions that
line up with their header token's x0, so we read word x-coordinates with pdfplumber
and bucket each number into the column whose header x0 it sits nearest-to-the-right
of, then attach the numbers to the closest product-name line above.

The trailing 'TOTAL' row prints the vendor's own grand totals (OPENING/CLOSING);
it is skipped as data. Numeric fragments inside a product name (pack sizes like
'180', '1000', pincode) live left of the OPENING column (x0 < ~250) and are never
bucketed.

KHURANA june.pdf (KLM PHARMA) column sums: OPENING 29 / RECEIPT 120 / ISSUE 118 /
CLOSING 15 — OPENING (29) and CLOSING (15) match the printed TOTAL row exactly.
20 product rows; 17 balance the CLOSING=OPENING+RECEIPT-ISSUE identity, the 3
residuals (GA-12, GA-6, MELAPIK-HQ) are genuine vendor stock-adjustment misprints
(closing printed lower/equal than the movement implies), not an extraction error.

Detect: gate on the title 'stock & sales analysis' together with the unique header
run 'item description' + 'opening'/'receipt'/'issue'/'closing'. 'item description'
appears in no other stock export, so the gate cannot steal any sibling analysis
variant (which carry their own vocab such as 'purchasesreturnothers'). It MUST be
placed before the coarse opening/receipt/issue/closing -> simple4 fallback.
"""
import io
import re

_HDR = ("OPENING", "RECEIPT", "ISSUE", "CLOSING")


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
    """If this word row is the column header, return {col: x0} else None."""
    by_text = {}
    for w in row_words:
        by_text.setdefault(w["text"].upper(), w)
    if not all(t in by_text for t in _HDR):
        return None
    return {t: by_text[t]["x0"] for t in _HDR}


def parse_stock_item_desc_oric_positional(text, file_bytes=None):
    if not file_bytes:
        return []
    import pdfplumber

    records = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            by_top = {}
            for w in words:
                by_top.setdefault(round(w["top"]), []).append(w)

            anchors = None
            # left x boundary of the first (OPENING) numeric column; anything left of
            # it is product-name / pack text (may itself carry digits).
            name_cut = None
            # ordered (col, x0) pairs for right-of-anchor bucketing
            hcols = None

            # product anchors: (top, name-tokens) accumulated as we scan top-down
            anchor_tops = []      # list of (top, name_str)
            per_anchor = {}       # top -> {col: value}

            for top in sorted(by_top):
                row_words = sorted(by_top[top], key=lambda w: w["x0"])

                if anchors is None:
                    found = _header_anchors(row_words)
                    if found:
                        anchors = found
                        hcols = sorted(anchors.items(), key=lambda kv: kv[1])
                        name_cut = hcols[0][1] - 6.0
                    continue

                joined = "".join(w["text"] for w in row_words)
                if joined and set(joined) <= set("-"):
                    continue  # dashed rule line

                # split this visual row into name tokens (left of the columns) and
                # numeric column tokens.
                name_tokens = [w for w in row_words if w["x1"] <= name_cut]
                col_tokens = [w for w in row_words if w["x0"] >= name_cut]

                name_str = " ".join(w["text"] for w in name_tokens).strip()

                # bucket numeric tokens by nearest column whose x0 they sit at/right of
                row_vals = {}
                for w in col_tokens:
                    t = w["text"]
                    if t == "-":
                        continue
                    if not _is_num(t):
                        continue
                    x0 = w["x0"]
                    chosen = None
                    for cname, hx in hcols:
                        if x0 >= hx - 6.0:
                            chosen = cname
                    if chosen is None:
                        continue
                    # keep first value seen for a column within this record window
                    row_vals.setdefault(chosen, _to_f(t))

                low = name_str.lower()
                is_total = low.startswith("total")

                if name_str and re.search(r"[A-Za-z]", name_str) and not is_total:
                    # a new product-name line opens a fresh record.
                    anchor_tops.append((top, name_str))
                    per_anchor[top] = dict(row_vals)
                elif row_vals:
                    # bare numeric wrap line (or the TOTAL row): attach the numbers
                    # to the most recent product anchor above, filling only empties.
                    if is_total:
                        continue  # vendor grand-total row, not a product
                    if anchor_tops:
                        cur = per_anchor[anchor_tops[-1][0]]
                        for k, v in row_vals.items():
                            cur.setdefault(k, v)

            for atop, name in anchor_tops:
                vals = per_anchor.get(atop, {})
                op = vals.get("OPENING", 0.0)
                rec = vals.get("RECEIPT", 0.0)
                iss = vals.get("ISSUE", 0.0)
                cls = vals.get("CLOSING", 0.0)
                name = re.sub(r"\s+", " ", name).strip()
                if not name or len(name) < 2:
                    continue
                # a band header such as a bare division label ('KLM LAB') carries no
                # numbers at all — skip it.
                if op == 0 and rec == 0 and iss == 0 and cls == 0 and not vals:
                    continue
                records.append({
                    "product_name": name,
                    "opening_stock": op,
                    "purchase_stock": rec,
                    "sales_qty": iss,
                    "closing_stock": cls,
                })
            # this export is a single division per PDF, one page — stop after page 0.
            if records:
                break

    return records
