"""KLM 'Stock And Sale Report(Month)' — Rcpt dialect (SHREE SHIVASAKTHI MEDICAL).

Sibling of ``klm_stock_sales_month`` / ``klm_stock_sales_month_repq``: same KLM
per-division export family, a third column vocabulary. Header row (single line):

  Product Name | Pack | OpStk | Rcpt | Apr2 | May2 | sales | Cl.S |
  StkValu | SalValu | Expiry | Age

``Apr2``/``May2`` are DYNAMIC previous-month sales columns (the two calendar
months before the report month; they rename every month, so we never gate on
their printed name — we anchor them positionally as the two header words between
``Rcpt`` and ``sales`` and then drop them). ``StkValu`` is the current/closing
stock rupee value (footer 'Current Stock Value'), ``SalValu`` the current-month
sales rupee value (footer 'Cur Sales'). ``Expiry``/``Age`` are trailing meta.
Core quantity movement:

  Cl.S (closing qty) = OpStk + Rcpt - sales

(there is no free / adj / return column in this dialect). ``Rcpt`` (receipts) is
the purchase inflow, ``sales`` the outflow.

Zero-movement products print their numeric cells BLANK, so a flat left/right text
split misaligns badly. The numbers are RIGHT-ALIGNED and every column's right edge
lines up exactly with the corresponding header token's x1 (measured on page-1 word
coords: OpStk 243.6, Rcpt 273.5, Apr2 303.5, May2 333.4, sales 369.4, Cl.S 399.3,
StkValu 447.3, SalValu 495.2, Age 573.1). We read word x-positions with pdfplumber
and bucket each numeric word into the column whose header x1 it aligns to.

Field mapping: opening_stock<-OpStk, purchase_stock<-Rcpt, sales_qty<-sales,
closing_stock<-Cl.S, closing_stock_value<-StkValu, sales_value<-SalValu; the two
dynamic prev-month columns and Expiry/Age are ignored.

Layout quirk (same export as the siblings): the ENTIRE report renders on every
physical page (3 pages here, differing only by a 'Page N / 3' footer and
interleaved 'Document Footer Text' glyphs), so we parse page 0 ONLY. The printed
grand-total row floats at the bottom of page 0 — sometimes interleaved with the
'Document Footer Text' glyph band — and is skipped by an empty/footer product name
(no product row would have a blank name).

Reconciliation (klm 3.PDF, COSMOCOR): printed grand total OpStk 440, Rcpt 385,
sales 348, Cl.S 481, StkValu 72465.42, SalValu 50856.05. Source residual: the
source itself only near-balances (440+385-348 = 477 vs printed Cl.S 481, off 4),
which the diagnosis flags as acceptable.
"""
import io
import re

_NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*$")

# header tokens that must ALL be present for a word-row to be the column header
_HDR_REQUIRED = ("OpStk", "Rcpt", "Cl.S", "StkValu", "SalValu")


def _is_num(t):
    t = t.replace(",", "")
    return bool(_NUM_RE.fullmatch(t)) and any(c.isdigit() for c in t)


def _to_f(t):
    try:
        return float(t.replace(",", ""))
    except ValueError:
        return 0.0


def _header_anchors(words):
    """If this word-row is the column header, return (order, x1s, name_cut) else None.

    ``order`` is the list of canonical column keys left-to-right, ``x1s`` the
    matching right-edge x1 anchors. Apr2/May2 (dynamic prev-month labels) are
    resolved positionally as the two header words strictly between Rcpt and
    'sales' and keyed 'M1'/'M2' so we never depend on the month name.
    """
    by_text = {}
    for w in words:
        by_text.setdefault(w["text"], w)  # first occurrence of each label
    if not all(t in by_text for t in _HDR_REQUIRED):
        return None
    # the outflow header word is lowercase 'sales' in this export
    sales = by_text.get("sales") or by_text.get("Sales")
    if sales is None:
        return None

    rcpt = by_text["Rcpt"]
    mid = sorted(
        (w for w in words if rcpt["x1"] < w["x0"] < sales["x0"]),
        key=lambda w: w["x0"],
    )

    anchors = {
        "OpStk": by_text["OpStk"]["x1"],
        "Rcpt": rcpt["x1"],
        "sales": sales["x1"],
        "Cl.S": by_text["Cl.S"]["x1"],
        "StkValu": by_text["StkValu"]["x1"],
        "SalValu": by_text["SalValu"]["x1"],
    }
    if len(mid) >= 2:
        anchors["M1"] = mid[0]["x1"]
        anchors["M2"] = mid[1]["x1"]

    order = [c for c in ("OpStk", "Rcpt", "M1", "M2", "sales", "Cl.S",
                         "StkValu", "SalValu") if c in anchors]
    x1s = [anchors[c] for c in order]
    name_cut = by_text["OpStk"]["x0"] - 3.0
    return order, x1s, name_cut


def parse_klm_stock_sales_month_rcpt(text, file_bytes=None):
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

        order = None
        x1s = None
        name_cut = None

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
                    if _is_num(w["text"])
                    and (w["x0"] + w["x1"]) / 2.0 >= name_cut]
            name = " ".join(
                w["text"] for w in row_words if w["x1"] <= name_cut
            ).strip()

            low = name.replace(" ", "").lower()
            # Grand-total row: no product name (or the interleaved 'Document
            # Footer Text' glyph band, or a bare 'Page N / 3'). No real product
            # row has a blank name — the grand-total row terminates the product
            # table, and everything below it is the 'Op.Stk.Value:/Purchase
            # Value:/Cur Sales' footer band (whose rupee cells would otherwise
            # bucket into StkValu/SalValu and inflate the value totals). Stop.
            if (not name or "documentfooter" in low or low.startswith("page")) \
                    and nums:
                break
            if name.startswith("~"):
                continue  # placeholder / discontinued item, no data
            if not nums:
                continue
            # footer band lines that carry a product-name-zone label
            if low.startswith(("op.stk.value", "purchasevalue", "prevsales",
                               "cursales", "currentstock", "endofreport",
                               "gobi")):
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
            sale = col.get("sales", 0.0)
            cls = col.get("Cl.S", 0.0)
            skv = col.get("StkValu", 0.0)
            slv = col.get("SalValu", 0.0)
            if op == 0 and rcpt == 0 and sale == 0 and cls == 0 \
                    and skv == 0 and slv == 0:
                continue  # band / all-blank / phantom row

            records.append({
                "product_name": name,
                "opening_stock": op,
                "purchase_stock": rcpt,
                "sales_qty": sale,
                "closing_stock": cls,
                "sales_value": slv,
                "closing_stock_value": skv,
            })

    return records
