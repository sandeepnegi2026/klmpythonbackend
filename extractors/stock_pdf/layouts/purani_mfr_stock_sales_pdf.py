"""PURANI HOSPITAL SUPPLIES PVT LTD — "MFR Stock and Sales Report" (HTML-print PDF).

Vendor : PURANI HOSPITAL SUPPLIES PRIVATE LIMITED (one PDF per KLM division:
         KLM COSMO / COSMOCOR / COSMOQ / DERMA / DERMACOR / PEDIA / PHARMA).
Format : an ERP report printed to PDF from the browser ("about:blank ... PURANI
         HOSPITAL SUPPLIES"). Every table cell is boxed, so the page carries >400
         rects and the coarse ``n_rects > 400 -> marg_bordered`` catch-all in
         detect.py steals the file and mis-binds the columns -> SANITY_FAILED.

         This is the PDF twin of the stock_xlsx purani_mfr_stock_sales layout: the
         same 18-column MFR Stock & Sales table. The PDF text layer heavily wraps
         each product name across several lines AND right-aligns every numeric
         column, so a flat text parse cannot align the columns; we read word
         x-positions with pdfplumber and bucket each number by its RIGHT edge (x1)
         against the printed header row (columns are right-aligned).

Header (18 cols):
    S.No | Particulars | Pack | O.St | Pur | Free | PRtn | MBMon | LMon | Mon |
    C.St | P.Qty | E.PO | Rate | Sales | Stock | Box | P.Dt

Column map (canonical):
    Particulars -> product_name (wrapped fragments stitched by S.No anchor)
    Pack        -> pack
    O.St        -> opening_stock
    Pur         -> purchase_stock
    Free        -> purchase_free
    PRtn        -> purchase_return
    Mon         -> sales_qty            (current-month sales quantity)
    C.St        -> closing_stock
    Rate        -> rate
    Sales       -> sales_value          (per-row cost of goods sold, as printed)
    Stock       -> closing_stock_value
  MBMon/LMon (prior-month qty) and P.Qty/E.PO/Box/P.Dt are ignored.

Reconcile equation (holds on ~93% of data rows across the 7 division files):
    C.St = O.St + Pur - Mon
  The residual ~7% are genuine source imbalances where the ERP posted a receipt
  into the wrong period column (e.g. a stray LMon=100 with Pur=1 yet closing 51).

  The vendor's printed "Total Value" block (Opening/Purchase/Sales/Closing Value)
  is computed on a running-average cost basis and therefore does NOT equal the sum
  of the frozen per-row Sales/Stock value columns; the per-row table values printed
  in the grid ARE captured faithfully.

Each PDF is a single division with a single current-month product table (no prior-
month blocks to de-dup, unlike the combined .xls). The trailing "Stock Received
During the Month" footer table has an S.No but no O.St/C.St cells and is skipped.
"""
import io
import re
import collections

_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?$")

# Column order left->right; the header carries these exact tokens.
_ORDER = ["O.St", "Pur", "Free", "PRtn", "MBMon", "LMon", "Mon",
          "C.St", "P.Qty", "E.PO", "Rate", "Sales", "Stock", "Box"]

# Product-name text lives between the Particulars header x0 and the Pack column.
_NAME_X0_MIN = 55.0
_NAME_X0_MAX = 128.0
# Tokens that print in the name x-band but are NOT part of the product name:
# the header labels themselves and the ERP's per-row pack marker ("`S").
_NAME_STOP = {"Particulars", "Pack", "`S"}
# Words that only appear in the trailing "Total Value" / "Stock Received" footer
# block; a name-band line carrying any of these is a footer line, not a product.
_FOOTER_WORDS = {"Value", "Month", "Opening", "Purchase", "Closing", "Free",
                 "Document", "Stock", "Sales", "Total", "PM", "AM", "Claim",
                 "Claim.NO", "Pending", "Cliam(s)", "about:blank"}
# Page-header timestamp fragment (e.g. "2:32") that prints in the name band.
_TIME_RE = re.compile(r"^\d{1,2}:\d{2}$")


def _is_num(t):
    return bool(_NUM_RE.fullmatch(t.replace(",", "")))


def _to_f(t):
    return float(t.replace(",", ""))


def _header_anchors(row_words):
    """If this word row is the column header, return {col: x1(right edge)}, else None."""
    lab = {w["text"]: w["x1"] for w in row_words}
    if "S.No" not in lab or "Particulars" not in lab or "C.St" not in lab or "PRtn" not in lab:
        return None
    anchors = {c: lab[c] for c in _ORDER if c in lab}
    return anchors if "O.St" in anchors and "C.St" in anchors else None


def parse_purani_mfr_stock_sales_pdf(text, file_bytes=None):
    if not file_bytes:
        return []
    import pdfplumber

    records = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        anchors = None
        for page in pdf.pages:
            words = page.extract_words()
            by_top = collections.defaultdict(list)
            for w in words:
                by_top[round(w["top"])].append(w)
            tops = sorted(by_top)

            # ---- pass 1: classify each line and pull the movement cells of data rows.
            # A "data" line is anchored by the integer S.No at the far left AND carries
            # both opening + closing cells (the "Stock Received" footer has neither).
            data_rows = []          # (top, col-dict)
            name_lines = []         # (top, [(x0, text), ...]) for pure product-name lines
            for top in tops:
                row_words = sorted(by_top[top], key=lambda w: w["x0"])

                found = _header_anchors(row_words)
                if found:
                    anchors = found
                    continue
                if not anchors:
                    continue

                order = [c for c in _ORDER if c in anchors]
                left_edge = anchors[order[0]] - 30.0
                has_sno = any(w["x0"] < 50 and w["text"].isdigit() for w in row_words)

                col = {}
                if has_sno:
                    x1s = [anchors[c] for c in order]
                    bounds = []
                    for i in range(len(x1s)):
                        lo = (x1s[i - 1] + x1s[i]) / 2.0 if i > 0 else x1s[i] - 30.0
                        hi = (x1s[i] + x1s[i + 1]) / 2.0 if i + 1 < len(x1s) else x1s[i] + 18.0
                        bounds.append((lo, hi))
                    for w in row_words:
                        if not _is_num(w["text"]) or w["x1"] < left_edge:
                            continue
                        for i, c in enumerate(order):
                            lo, hi = bounds[i]
                            if lo <= w["x1"] < hi:
                                col[c] = _to_f(w["text"])
                                break

                if has_sno and "O.St" in col and "C.St" in col:
                    data_rows.append((top, col))

                # Product-name fragments (may co-exist on a data anchor line, e.g. a
                # short first name-word that fits before the numbers).
                frags = [(w["x0"], w["text"]) for w in row_words
                         if _NAME_X0_MIN <= w["x0"] <= _NAME_X0_MAX
                         and not _is_num(w["text"])
                         and w["text"] not in _NAME_STOP
                         and not _TIME_RE.match(w["text"])]
                # Drop footer / page-header lines ("Total Value", "Month Sales Value",
                # "2:32 PM ... Claim.NO", ...) unless this is itself a data anchor line
                # (a real product row never carries a footer keyword in its name band).
                if frags and not has_sno and any(t in _FOOTER_WORDS for _, t in frags):
                    frags = []
                if frags:
                    name_lines.append((top, frags))

            if not data_rows:
                continue

            # ---- pass 2: bind each name fragment line to the nearest data anchor.
            anchor_tops = [t for t, _ in data_rows]
            name_by_anchor = collections.defaultdict(list)
            for ntop, frags in name_lines:
                nearest = min(anchor_tops, key=lambda at: abs(at - ntop))
                name_by_anchor[nearest].append((ntop, frags))

            for atop, col in data_rows:
                parts = []
                for ntop, frags in sorted(name_by_anchor.get(atop, [])):
                    for x0, txt in sorted(frags):
                        parts.append((ntop, x0, txt))
                name = re.sub(r"\s+", " ",
                              " ".join(t for _, _, t in sorted(parts))).strip()
                records.append({
                    "product_name": name,
                    "opening_stock": col.get("O.St", 0.0),
                    "purchase_stock": col.get("Pur", 0.0),
                    "purchase_free": col.get("Free", 0.0),
                    "purchase_return": col.get("PRtn", 0.0),
                    "sales_qty": col.get("Mon", 0.0),
                    "closing_stock": col.get("C.St", 0.0),
                    "rate": col.get("Rate", 0.0),
                    "sales_value": col.get("Sales", 0.0),
                    "closing_stock_value": col.get("Stock", 0.0),
                })
    return records
