"""KLM (custom KLM ERP) "CLOSING STOCK REPORT FROM .. TO .." — one file per
COMPANY / division (KLM COSMO, KLM COSMO COR, KLM COSMO Q, KLM DERMA,
KLM DERMA COR, KLM PHARMA, KLM GYNAE/PAEDIATRIC).

Single flat table, NO party column (banding is by company printed in the header
block). Fixed column order:

    SNO | ITEM NAME | PACKING | OP STK (opening qty) | PUR QTY | PUR VALUE |
    SALE QTY | SALE VALUE | FREE | CL STOCK (closing qty) | CLOSING VALUE

The numeric columns are RIGHT-ALIGNED and interior cells print BLANK for
no-movement rows (a purchase-only / sale-only / opening-only item omits whole
column pairs), so the flat text layer carries a VARIABLE number of trailing
numbers (3-8) and their left-to-right index no longer identifies the column.
The item name also glyph-interleaves with the packing/first number on wrapped
rows.  We therefore parse by word x-position: cluster words into visual rows and
bucket each numeric token into its column by the RIGHT edge (x1), which is
stable across every file in this KLM export.

Reconciliation:  the FREE column is free goods GIVEN OUT with the sale (an
outflow), so CL STOCK ~= OP + PUR - SALE - FREE.  Many rows reconcile exactly
(e.g. NIOFINE TAB 44 + 50 - 32 - 8 = 54; RESOTEN-20 41 - 9 - 3 = 29), while a
minority carry genuine unshown adjustments/returns so it only holds
approximately in aggregate.  FREE therefore maps to sales_free.  This is genuine
stock data with a value grand-total — report_type=stock.
"""
import io
import re

# Right edges (x1) of each numeric column, read off the KLM export geometry.
# Numbers are right-aligned, so we bucket a token by the boundary its x1 falls
# under. Boundaries are the midpoints between consecutive column right edges.
#   OP STK ~164 | PUR QTY ~194 | PUR VALUE ~252 | SALE QTY ~293 |
#   SALE VALUE ~358 | FREE ~393 | CL STOCK ~440 | CLOSING VALUE ~516
_COL_BOUNDS = [
    (179.0, "op"),      # x1 <= 179  -> OP STK QTY
    (223.0, "pur"),     # 179 < x1 <= 223 -> PUR QTY
    (272.0, "purval"),  # 223 < x1 <= 272 -> PUR VALUE
    (325.0, "saleqty"), # 272 < x1 <= 325 -> SALE QTY
    (375.0, "saleval"), # 325 < x1 <= 375 -> SALE VALUE
    (416.0, "free"),    # 375 < x1 <= 416 -> FREE
    (478.0, "cl"),      # 416 < x1 <= 478 -> CL STOCK QTY
    (99999.0, "clval"), # x1 > 478   -> CLOSING VALUE
]

_NAME_X_MAX = 113.0   # ITEM NAME tokens live at x0 22..~113
_PACK_X_MAX = 148.0   # PACKING tokens live at x0 ~115..~148
_NUM_X_MIN = 145.0    # numeric columns begin at OP STK (x0 ~149); guard packing

_NUM_RE = re.compile(r"^-?\d[\d,]*\.?\d*$")


def _is_num(t):
    t = t.replace(",", "")
    return bool(_NUM_RE.fullmatch(t)) and any(c.isdigit() for c in t)


def _to_f(t):
    try:
        return float(t.replace(",", ""))
    except ValueError:
        return 0.0


def _bucket(x1):
    for bound, name in _COL_BOUNDS:
        if x1 <= bound:
            return name
    return "clval"


def _cluster_rows(words, tol=6):
    """Group words into visual rows: tops within `tol` px of the cluster's first
    top belong together (folds the 1-2 px sub-line jitter that splits a row)."""
    by_top = {}
    for w in words:
        by_top.setdefault(round(w["top"]), []).append(w)
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


def parse_klm_closing_stock_report(text, file_bytes=None):
    if not file_bytes:
        return []
    import pdfplumber

    records = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            for row_words in _cluster_rows(words):
                row_words = sorted(row_words, key=lambda w: w["x0"])

                cols = {}
                name_toks, pack_toks = [], []
                has_serial = False
                for w in row_words:
                    t = w["text"]
                    x0, x1 = w["x0"], w["x1"]
                    if _is_num(t) and x1 >= _NUM_X_MIN:
                        b = _bucket(x1)
                        # keep the first token seen for a column (guards a stray
                        # split-digit landing twice in the same bucket)
                        cols.setdefault(b, _to_f(t))
                    elif _is_num(t) and x0 < 40:
                        has_serial = True  # leading SNO serial column
                    elif x0 < _NAME_X_MAX:
                        name_toks.append(t)
                    elif x0 < _PACK_X_MAX:
                        pack_toks.append(t)
                    # tokens between pack and numbers with letters -> ignore
                    elif not _is_num(t):
                        pack_toks.append(t)

                if not cols:
                    continue

                # Skip the printed grand-total footer: it has NO serial and NO
                # item name (just the summed numbers on the last line).
                name = " ".join(name_toks).strip()
                low = name.lower()
                if "total" in low or low.startswith("page") or low.startswith("company"):
                    continue
                if not name and not has_serial:
                    continue

                op = cols.get("op", 0.0)
                pur = cols.get("pur", 0.0)
                purval = cols.get("purval", 0.0)
                saleqty = cols.get("saleqty", 0.0)
                saleval = cols.get("saleval", 0.0)
                free = cols.get("free", 0.0)
                cl = cols.get("cl", 0.0)
                clval = cols.get("clval", 0.0)

                if op == 0 and pur == 0 and saleqty == 0 and cl == 0 and clval == 0:
                    continue

                pack = " ".join(pack_toks).strip()
                r = {
                    "product_name": name,
                    "pack": pack,
                    "opening_stock": op,
                    "purchase_stock": pur,
                    "purchase_value": purval,
                    "sales_qty": saleqty,
                    "sales_value": saleval,
                    "sales_free": free,   # FREE = free goods given with sale (outflow)
                    "closing_stock": cl,
                    "closing_stock_value": clval,
                }
                records.append(r)
    return records
