"""KLM 'Stock And Sales Report(Month)' — RepQ dialect (JEYANTHI PHARMAA).

Sibling of ``klm_stock_sales_month`` (YOGIRAM PHARMA): same per-division KLM
export family, different column vocabulary. Header row (single line):

  ProductName | Pack | OpSt | PurQ | Mar | Apr | Sale | Free | RepQ |
  SaleValue | Stock | StockValue | LPD

``Mar``/``Apr`` are DYNAMIC month-abbreviation columns (the two calendar months
before the report month — informational prior-month sales; ignored). ``Stock`` is
the closing quantity, ``StockValue`` the closing rupee value, ``LPD`` a trailing
last-purchase date (non-numeric). Core quantity movement:

  Stock (closing qty) = OpSt + PurQ - Sale - Free - RepQ

where ``Free`` is a free-goods outflow and ``RepQ`` is a replacement outflow.

Zero-movement products print their numeric cells BLANK, so a flat left/right text
split misaligns badly (e.g. 'HERPIVAL-500MG 3'S 20 0 0 0 20 2200.55 07/03/26' has
only 6 of 10 numbers). We read word x-positions with pdfplumber and bucket each
numeric word into a column. This dialect uses MIXED alignment (measured on
page-1 word coords):

  * OpSt / PurQ / SaleValue / StockValue values RIGHT-align to the header x1;
  * Mar / Apr / Sale / Free / RepQ / Stock values LEFT-align to the header x0.

So the sibling's x1-only bucketing fails here — we bucket a word into a column iff
``|w.x0 - c.x0| < 3`` OR ``|w.x1 - c.x1| < 3`` (verified exact on every sampled
cell; the GRN invoice amounts below the table match nothing at 3.0pt).

Layout quirk (same export as the sibling): the ENTIRE report renders on every
physical page (pages differ only by a 'Page N / 4' footer and interleaved
'Document Footer Text' glyphs). Below the product table sits a numeric grand-total
row aligned under Sale..StockValue, then an 'Invoice Details' GRN table and a
'Purchase Return Details' table whose GRN rows lead with a dd/mm/yy date and whose
rupee amounts collide with the Sale x-column. We therefore STOP scanning a page's
tops once we have recorded the grand-total row, and STOP the page loop after the
first page that carries it (the whole report is on page 1). In PEDIA the
grand-total row's top is shared by the interleaved footer glyph band
('D o c u m e n t F o o t er T e x t'), so the grand-total detector also accepts a
name whose compacted lowercase contains 'documentfooter'.

Field mapping: opening_stock<-OpSt, purchase_stock<-PurQ, sales_qty<-Sale,
sales_free<-Free (outflow), purchase_return<-RepQ (replacement outflow;
postprocess.sanity_warnings expects closing = op+pur+pf-pr-sal-sf+sr, so RepQ as
purchase_return is subtracted), closing_stock<-Stock, sales_value<-SaleValue,
closing_stock_value<-StockValue; Mar/Apr/LPD ignored.
"""
import io
import re

_NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*$")

# header tokens that must ALL be present for a word-row to be the column header
_HDR_REQUIRED = ("ProductName", "OpSt", "PurQ", "Sale", "Free", "RepQ",
                 "Stock", "StockValue", "LPD")

# canonical column name -> (header label, alignment) for the ten value columns,
# in printed left-to-right order. 'M1'/'M2' are the dynamic prev-month columns
# (labels 'Mar'/'Apr' this export, renamed next month) and are never referenced
# by their printed name — we anchor them positionally by taking the header words
# between PurQ and Sale.
_VALUE_COLS = ["OpSt", "PurQ", "M1", "M2", "Sale", "Free", "RepQ",
               "SaleValue", "Stock", "StockValue"]

_TOL = 3.0  # x0 / x1 bucketing tolerance (pt)

# lowered joined-name fragments that mark a non-product row to skip
_SKIP_NAME_PREFIX = (
    "document", "page", "total", "grn", "invoice", "current", "last",
    "2nd", "sales return", "purchase return",
)

_DATE_LEAD_RE = re.compile(r"^\d{2}/\d{2}/\d{2,4}\b")


def _is_num(t):
    t = t.replace(",", "")
    return bool(_NUM_RE.fullmatch(t)) and any(c.isdigit() for c in t)


def _to_f(t):
    try:
        return float(t.replace(",", ""))
    except ValueError:
        return 0.0


def _header_anchors(words):
    """If this word-row is the column header, return (anchors, name_cut) else None.

    anchors maps each canonical column name in _VALUE_COLS to (x0, x1) of the
    header word that owns it (the two dynamic prev-month columns 'M1'/'M2' are
    the header words positioned between PurQ and Sale, taken in x-order).
    """
    by_text = {}
    for w in words:
        by_text.setdefault(w["text"], w)  # first occurrence of each label
    if not all(t in by_text for t in _HDR_REQUIRED):
        return None

    purq = by_text["PurQ"]
    sale = by_text["Sale"]
    # dynamic prev-month header words sit strictly between PurQ and Sale
    mid = sorted(
        (w for w in words if purq["x1"] < w["x0"] < sale["x0"]),
        key=lambda w: w["x0"],
    )
    anchors = {
        "OpSt": (by_text["OpSt"]["x0"], by_text["OpSt"]["x1"]),
        "PurQ": (purq["x0"], purq["x1"]),
        "Sale": (sale["x0"], sale["x1"]),
        "Free": (by_text["Free"]["x0"], by_text["Free"]["x1"]),
        "RepQ": (by_text["RepQ"]["x0"], by_text["RepQ"]["x1"]),
        "SaleValue": (by_text["SaleValue"]["x0"], by_text["SaleValue"]["x1"]),
        "Stock": (by_text["Stock"]["x0"], by_text["Stock"]["x1"]),
        "StockValue": (by_text["StockValue"]["x0"], by_text["StockValue"]["x1"]),
    }
    if len(mid) >= 2:
        anchors["M1"] = (mid[0]["x0"], mid[0]["x1"])
        anchors["M2"] = (mid[1]["x0"], mid[1]["x1"])
    name_cut = by_text["OpSt"]["x0"] - 2.0
    return anchors, name_cut


def _bucket(w, anchors):
    """Return the canonical column name for a numeric word, or None (mixed
    alignment: match left edge OR right edge within tolerance)."""
    x0, x1 = w["x0"], w["x1"]
    best_name, best_d = None, _TOL
    for name in _VALUE_COLS:
        if name not in anchors:
            continue
        cx0, cx1 = anchors[name]
        d = min(abs(x0 - cx0), abs(x1 - cx1))
        if d < best_d:
            best_d, best_name = d, name
    return best_name


def parse_klm_stock_sales_month_repq(text, file_bytes=None):
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
            name_cut = None
            saw_grand_total = False

            for top in sorted(by_top):
                row_words = sorted(by_top[top], key=lambda w: w["x0"])

                found = _header_anchors(row_words)
                if found:
                    anchors, name_cut = found
                    continue
                if not anchors:
                    continue

                joined = "".join(w["text"] for w in row_words)
                if joined and set(joined) <= set("-"):
                    continue  # dashed rule line

                name = " ".join(
                    w["text"] for w in row_words if w["x1"] <= name_cut
                ).strip()

                col = {}
                for w in row_words:
                    if not _is_num(w["text"]):
                        continue
                    if w["x1"] <= name_cut:
                        continue  # numeric token inside the product-name zone
                    c = _bucket(w, anchors)
                    if c is not None:
                        col.setdefault(c, _to_f(w["text"]))

                op = col.get("OpSt", 0.0)
                pur = col.get("PurQ", 0.0)
                sale = col.get("Sale", 0.0)
                free = col.get("Free", 0.0)
                rep = col.get("RepQ", 0.0)
                cls = col.get("Stock", 0.0)

                # GRAND-TOTAL row: buckets land only in Sale/Free/RepQ/SaleValue/
                # Stock/StockValue with OpSt/PurQ/M1/M2 absent, AND the name is
                # empty OR carries the interleaved footer band (PEDIA). Record it,
                # then STOP — everything below is the GRN / purchase-return tables.
                low = name.replace(" ", "").lower()
                head_absent = not any(
                    k in col for k in ("OpSt", "PurQ", "M1", "M2")
                )
                tail_present = any(
                    k in col for k in
                    ("Sale", "Free", "RepQ", "SaleValue", "Stock", "StockValue")
                )
                if head_absent and tail_present and (
                        not name or "documentfooter" in low):
                    saw_grand_total = True
                    break

                if not name:
                    continue
                if name.startswith("~"):
                    continue  # placeholder / discontinued item, no data
                if _DATE_LEAD_RE.match(name):
                    continue  # GRN invoice / purchase-return row
                if name.lower().startswith(_SKIP_NAME_PREFIX):
                    continue
                # division band ('KLM-COSMO') and other numeric-free rows
                if op == 0 and pur == 0 and sale == 0 and free == 0 \
                        and rep == 0 and cls == 0:
                    continue

                records.append({
                    "product_name": name,
                    "opening_stock": op,
                    "purchase_stock": pur,
                    "sales_qty": sale,
                    "sales_free": free,
                    "purchase_return": rep,
                    "closing_stock": cls,
                    "sales_value": col.get("SaleValue", 0.0),
                    "closing_stock_value": col.get("StockValue", 0.0),
                })

            # The whole report is on page 1; once we have the grand-total tail we
            # have every product row — stop so nothing is emitted N times.
            if saw_grand_total and records:
                break

    return records
