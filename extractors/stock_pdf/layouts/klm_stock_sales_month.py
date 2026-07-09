"""KLM 'Stock And Sales Report(Month)' — one report per division (YOGIRAM PHARMA).

Header row:
  ProductName | Pack | Apr | May | OpSt | Pur | Sale | Free | Adj | Cl.S |
  SalesVal | CloStkVa | Age | POQty

Apr/May are the two previous-month sales columns (ignored). Core quantity movement:
  Cl.S (closing qty) = OpSt + Pur - Sale - Free + Adj
where Free is an outflow (free goods given) and Adj is a signed manual adjustment.
SalesVal / CloStkVa are the sales & closing-stock rupee values; Age / POQty are
trailing meta (order quantity).

Zero-movement products print their numeric cells BLANK, so a flat left/right text
split misaligns badly. The numbers are RIGHT-ALIGNED and every column's right edge
lines up exactly with the corresponding header token's x1, so we read word
x-positions with pdfplumber and bucket each number into the column whose header x1
it aligns to (small tolerance). The product name is the tokens left of the Apr
column; '~'-prefixed names are placeholder/discontinued items with no data.

Layout quirk: this export renders the ENTIRE report on every physical page (each
pdfplumber page returns all words, only shifted vertically and viewport-clipped), so
we stop after the first page that carries the printed grand-total tail to avoid
emitting the report N times. A 'Page x / y' footer and a 'Document Footer Text'
band float in the middle of the coordinate space and are skipped by name.

Secondary movement folding (marg_open_pur_free_sale / pharmassist_mfac precedent):
Free -> sales_free (outflow). A positive Adj is a net inflow correction and folds
into purchase_free; a negative Adj folds into sales_free — so the canonical
reconciliation closing = opening + purchase + purchase_free - sales - sales_free
holds without an extra field.
"""
import io
import re

_NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*$")

# header tokens that must ALL be present for a row to be the column header
_HDR_REQUIRED = ("ProductName", "OpSt", "Pur", "Sale", "Free", "Adj", "Cl.S")
# columns in printed left-to-right order; bucketed by RIGHT edge (x1)
_COLS = ["Apr", "May", "OpSt", "Pur", "Sale", "Free", "Adj", "Cl.S",
         "SalesVal", "CloStkVa", "Age", "POQty"]


def _is_num(t):
    t = t.replace(",", "")
    return bool(_NUM_RE.fullmatch(t)) and any(c.isdigit() for c in t)


def _to_f(t):
    try:
        return float(t.replace(",", ""))
    except ValueError:
        return 0.0


def _header_anchors(words):
    """If this word row is the column header, return (x1_by_col, apr_x0) else None."""
    by_text = {}
    for w in words:
        # keep the first occurrence of each header label
        by_text.setdefault(w["text"], w)
    if not all(t in by_text for t in _HDR_REQUIRED):
        return None
    anchors = {}
    for name in _COLS:
        if name in by_text:
            anchors[name] = by_text[name]["x1"]  # right edge
    if "OpSt" not in anchors or "Cl.S" not in anchors:
        return None
    apr_x0 = by_text["Apr"]["x0"] if "Apr" in by_text else 121.0
    return anchors, apr_x0


def parse_klm_stock_sales_month(text, file_bytes=None):
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
            order = None
            x1s = None
            name_cut = None
            saw_grand_total = False

            for top in sorted(by_top):
                row_words = sorted(by_top[top], key=lambda w: w["x0"])
                found = _header_anchors(row_words)
                if found:
                    anchors, apr_x0 = found
                    order = [c for c in _COLS if c in anchors]
                    x1s = [anchors[c] for c in order]
                    name_cut = apr_x0 - 6.0
                    continue
                if not anchors:
                    continue

                joined = "".join(w["text"] for w in row_words)
                if joined and set(joined) <= set("-"):
                    continue  # dashed rule line

                nums = [w for w in row_words
                        if _is_num(w["text"]) and (w["x0"] + w["x1"]) / 2.0 >= name_cut]
                name = " ".join(
                    w["text"] for w in row_words if w["x1"] <= name_cut
                ).strip()

                # empty-name rows: printed grand-total tail (huge values) or a
                # 'Page x / y' / footer band floating in the coordinate space.
                if not name:
                    if nums and any(_to_f(w["text"]) >= 10000 for w in nums):
                        saw_grand_total = True
                    continue

                if name.startswith("~"):
                    continue  # placeholder / discontinued item, no data
                low = name.lower()
                if low.startswith(("document", "page")) or "grand total" in low:
                    continue
                if not nums:
                    continue

                col = {}
                for w in nums:
                    xr = w["x1"]
                    best_i, best_d = None, 6.0
                    for i, xc in enumerate(x1s):
                        d = abs(xr - xc)
                        if d < best_d:
                            best_d, best_i = d, i
                    if best_i is not None:
                        col[order[best_i]] = _to_f(w["text"])

                op = col.get("OpSt", 0.0)
                pur = col.get("Pur", 0.0)
                sale = col.get("Sale", 0.0)
                free = col.get("Free", 0.0)
                adj = col.get("Adj", 0.0)
                cls = col.get("Cl.S", 0.0)
                if op == 0 and pur == 0 and sale == 0 and free == 0 and cls == 0:
                    continue  # all-blank / phantom row

                # fold signed Adj so canonical closing reconciles:
                #   +Adj  -> purchase_free (net inflow correction)
                #   -Adj  -> sales_free    (net outflow correction)
                purchase_free = adj if adj > 0 else 0.0
                sales_free = free + (-adj if adj < 0 else 0.0)

                records.append({
                    "product_name": name,
                    "opening_stock": op,
                    "purchase_stock": pur,
                    "purchase_free": purchase_free,
                    "sales_qty": sale,
                    "sales_free": sales_free,
                    "closing_stock": cls,
                    "sales_value": col.get("SalesVal", 0.0),
                    "closing_stock_value": col.get("CloStkVa", 0.0),
                    "order_qty": col.get("POQty", 0.0),
                })

            # This export repeats the whole report on every physical page; once we
            # have consumed a page carrying the grand-total tail, we have the full
            # report — stop so rows are not emitted N times.
            if saw_grand_total and records:
                break

    return records
