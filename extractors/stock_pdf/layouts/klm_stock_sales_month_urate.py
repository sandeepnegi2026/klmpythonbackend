"""KLM 'Stock And Sales Report(Month)' — U.Rate dialect (NAGAMMAI PHARMA).

Fourth sibling of ``klm_stock_sales_month`` / ``_repq`` / ``_rcpt``: the same KLM
per-division "Stock And Sales Report(Month)" export family, a distinct column
vocabulary. Header row (single line):

  Product Name | Pack | OpStk | Rcpt | AprL | Sale | ClStk | U.Rate |
  Sal Val | Stk Val | TfrOu

``AprL`` is a DYNAMIC previous-month sales column (renamed every month), so we
never gate on its printed name — we anchor it positionally as the single header
word between ``Rcpt`` and ``Sale`` and drop it. ``U.Rate`` is the unit rate,
``Sal Val`` the current-month sales rupee value, ``Stk Val`` the closing-stock
rupee value, ``TfrOu`` a transfer-out (outflow, usually blank). Core movement:

  ClStk (closing qty) = OpStk + Rcpt - Sale - TfrOu

(there is no free / adj / purchase-return column in this dialect). ``Rcpt`` is the
purchase inflow, ``Sale`` the outflow. Verified on all 7 NAGAMMAI division books:
80-100% of stocked rows reconcile; the few residuals are the vendor's own
near-balances (e.g. ZYCOZOL XL 34+20-24 = 30 vs printed ClStk 29), flagged
acceptable by the sanity note.

Zero-movement products print their numeric cells BLANK, so a flat left/right text
split misaligns. The numbers are RIGHT-ALIGNED, so we read word x-positions with
pdfplumber and bucket each numeric word into the column whose header right-edge
(x1) it aligns to. The two value columns are two-word headers ('Sal Val' /
'Stk Val'); their right edges are the x1 of the FIRST and SECOND 'Val' word.

Layout quirk (shared with the ``_rcpt`` sibling): the ENTIRE report renders on
every physical page (4 identical pages here, differing only by footer glyphs), so
we parse page 0 ONLY. The printed 'Grand Total' / 'Total <value>' footer floats at
the bottom of page 0 and is skipped by its blank product-name zone.

Field mapping: opening_stock<-OpStk, purchase_stock<-Rcpt, sales_qty<-Sale,
closing_stock<-ClStk, rate<-U.Rate, sales_value<-Sal Val,
closing_stock_value<-Stk Val, sales_free<-TfrOu (outflow); AprL is dropped.

Gate (compact, spaces stripped): 'stockandsalesreport(month)' + 'clstku.rate' +
'salvalstkval' — the U.Rate column and the SalVal-before-StkVal order are unique
to this dialect (the _rcpt sibling carries 'cl.sstkvalusalvalu', disjoint).
"""
import io
import re

_NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*$")

# header tokens that must ALL be present (stable, non-renaming) for the header row
_HDR_REQUIRED = ("OpStk", "Rcpt", "Sale", "ClStk", "U.Rate")


def _is_num(t):
    t = t.replace(",", "")
    return bool(_NUM_RE.fullmatch(t)) and any(c.isdigit() for c in t)


def _to_f(t):
    try:
        return float(t.replace(",", ""))
    except ValueError:
        return 0.0


def _header_anchors(words):
    """If this word-row is the column header, return (order, x1s, name_cut) else None."""
    by_text = {}
    for w in words:
        by_text.setdefault(w["text"], w)  # first occurrence of each label
    if not all(t in by_text for t in _HDR_REQUIRED):
        return None

    # The two value columns are two-word headers 'Sal Val' / 'Stk Val'; use the two
    # 'Val' words (left->right) as their right-edge anchors.
    vals = sorted((w for w in words if w["text"] == "Val"), key=lambda w: w["x0"])
    if len(vals) < 2:
        return None

    rcpt = by_text["Rcpt"]
    sale = by_text["Sale"]
    # AprL (dynamic prev-month) = the single header word strictly between Rcpt and Sale.
    mid = sorted(
        (w for w in words if rcpt["x1"] < w["x0"] < sale["x0"]),
        key=lambda w: w["x0"],
    )

    anchors = {
        "OpStk": by_text["OpStk"]["x1"],
        "Rcpt": rcpt["x1"],
        "Sale": sale["x1"],
        "ClStk": by_text["ClStk"]["x1"],
        "U.Rate": by_text["U.Rate"]["x1"],
        "SalVal": vals[0]["x1"],
        "StkVal": vals[1]["x1"],
    }
    if mid:
        anchors["M1"] = mid[0]["x1"]
    tfr = next((w for w in words if w["text"].startswith("TfrOu")), None)
    if tfr:
        anchors["TfrOu"] = tfr["x1"]

    order = [c for c in ("OpStk", "Rcpt", "M1", "Sale", "ClStk", "U.Rate",
                         "SalVal", "StkVal", "TfrOu") if c in anchors]
    x1s = [anchors[c] for c in order]
    name_cut = by_text["OpStk"]["x0"] - 3.0
    return order, x1s, name_cut


def parse_klm_stock_sales_month_urate(text, file_bytes=None):
    if not file_bytes:
        return []
    import pdfplumber

    records = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        # The whole report is replicated on every physical page — parse page 0 only.
        page = pdf.pages[0]
        words = page.extract_words()
        by_top = {}
        for w in words:
            by_top.setdefault(round(w["top"]), []).append(w)

        order = x1s = name_cut = None
        for top in sorted(by_top):
            row_words = sorted(by_top[top], key=lambda w: w["x0"])

            found = _header_anchors(row_words)
            if found:
                order, x1s, name_cut = found
                continue
            if not order:
                continue

            joined = "".join(w["text"] for w in row_words)
            if joined and set(joined) <= set("-"):
                continue  # dashed rule line

            nums = [w for w in row_words
                    if _is_num(w["text"]) and (w["x0"] + w["x1"]) / 2.0 >= name_cut]
            name = " ".join(w["text"] for w in row_words if w["x1"] <= name_cut).strip()

            low = name.replace(" ", "").lower()
            # Grand-total / footer band terminates the product table (blank name zone,
            # or a 'Grand Total'/'Total' rupee row). No real product row has a blank name.
            if (not name or low.startswith(("grandtotal", "total"))) and nums:
                break
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
                    col.setdefault(order[best_i], _to_f(w["text"]))

            op = col.get("OpStk", 0.0)
            rcpt = col.get("Rcpt", 0.0)
            sale = col.get("Sale", 0.0)
            cls = col.get("ClStk", 0.0)
            rate = col.get("U.Rate", 0.0)
            slv = col.get("SalVal", 0.0)
            skv = col.get("StkVal", 0.0)
            tfr = col.get("TfrOu", 0.0)
            if not any([op, rcpt, sale, cls, slv, skv, tfr]):
                continue  # all-blank / band / phantom row

            rec = {
                "product_name": name,
                "opening_stock": op,
                "purchase_stock": rcpt,
                "sales_qty": sale,
                "closing_stock": cls,
                "sales_value": slv,
                "closing_stock_value": skv,
            }
            if rate:
                rec["rate"] = rate
            if tfr:
                rec["sales_free"] = tfr   # TfrOu = transfer-out, outflow
            records.append(rec)

    return records
