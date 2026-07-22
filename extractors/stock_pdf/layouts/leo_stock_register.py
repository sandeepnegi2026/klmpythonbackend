"""LEO PHARMA DISTRIBUTORS "Stock Register" — KLM per-division export.

Title 'Stock Register - KLM LABORATORIES PVT LTD (<DIVISION>) -Period : ...', one
1-page report per division. Single fixed-width header, DASH-padded (every zero cell
prints '-'):

  PRODUCT NAME | OPENING | P.QTY | P.FR | STN | S.RTN | P.RTN | STNO | S.FREE |
  ADJ | CL.STK | CL.VALUE | S.QTY | S.VALUE

The vendor prints the column legend in the footer, which pins the mapping exactly:
  P.QTY=Purchase Qty, P.FR=Purchase Free, STN=Stock transfer IN, S.RTN=Sales Return,
  P.RTN=Purchase Return, STNO=Stock transfer OUT, S.FREE=Sales Free, ADJ=Adjustment,
  CL.STK=Closing Stock, CL.VALUE=Closing Stock Value, S.QTY=Sales Qty, S.VALUE=Sales Value.

A plain last-13-token text split ALMOST works, but combo-pack rows glyph-mangle their
pack into the name zone ('50+60ML' -> '50+ 60 1M4L', '60G+60G' -> '6 02G8+60G'),
injecting stray tokens that shift the tail and DROP those rows (fails the printed
Total Stock Value reconcile). So we read word x-positions with pdfplumber: the 13
data columns are RIGHT-ALIGNED, each value's x1 lines up with its header token's x1,
and the mangled pack tokens sit LEFT of the OPENING column (in the name zone), so
x-bucketing separates them cleanly.

Reconciles 100% on all 7 LEO division books, and every book's extracted CL.VALUE /
S.VALUE sums match the printed 'Total Stock Value' / 'Total Sales Value' footers:
  CL.STK = OPENING + P.QTY + P.FR + STN + S.RTN - P.RTN - STNO - S.QTY - S.FREE + ADJ

Canonical mapping (closing = opening + purchase + purchase_free - purchase_return
- sales_qty - sales_free + sales_return):
  OPENING -> opening_stock          P.QTY  -> purchase_stock
  P.FR    -> purchase_free (in)      STN    -> purchase_free  (transfer-in, in)
  S.RTN   -> sales_return (in)       P.RTN  -> purchase_return (out)
  STNO    -> purchase_return (transfer-out, out)   S.FREE -> sales_free (out)
  ADJ     -> signed: +ve sales_return / -ve purchase_return
  CL.STK  -> closing_stock           CL.VALUE -> closing_stock_value
  S.QTY   -> sales_qty               S.VALUE  -> sales_value

Gate: 'stockregister' title + the compact header run 'p.frstns.rtnp.rtnstno'
(P.FR STN S.RTN P.RTN STNO — the transfer-in/out pair is unique to this export).
"""
import io
import re

_NUM = re.compile(r"^-?\d[\d,]*\.?\d*$|^-$")
_ORDER = ["OPENING", "P.QTY", "P.FR", "STN", "S.RTN", "P.RTN", "STNO", "S.FREE",
          "ADJ", "CL.STK", "CL.VALUE", "S.QTY", "S.VALUE"]


def _val(t):
    if t == "-":
        return 0.0
    try:
        return float(t.replace(",", ""))
    except ValueError:
        return None


def _header(words):
    by = {w["text"]: w for w in words}
    if not ("OPENING" in by and "CL.STK" in by and all(c in by for c in _ORDER)):
        return None
    x1s = [by[c]["x1"] for c in _ORDER]
    return x1s, by["OPENING"]["x0"] - 3.0


def parse_leo_stock_register(text, file_bytes=None):
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

            x1s = name_cut = None
            for top in sorted(by_top):
                row = sorted(by_top[top], key=lambda w: w["x0"])
                hdr = _header(row)
                if hdr:
                    x1s, name_cut = hdr
                    continue
                if x1s is None:
                    continue

                nums = [w for w in row
                        if _NUM.match(w["text"]) and (w["x0"] + w["x1"]) / 2.0 >= name_cut]
                name = " ".join(w["text"] for w in row if w["x1"] <= name_cut).strip()
                low = name.lower()
                if (not name or low.startswith(("total", "grand", "page", "----",
                                                "p.qty", "cl.stk", "p.rtn"))):
                    continue
                if not nums:
                    continue

                col = {}
                for w in nums:
                    xr = w["x1"]
                    best_i, best_d = None, 8.0
                    for i, xc in enumerate(x1s):
                        d = abs(xr - xc)
                        if d < best_d:
                            best_d, best_i = d, i
                    if best_i is not None:
                        col.setdefault(_ORDER[best_i], _val(w["text"]))

                d = {c: (col.get(c) or 0.0) for c in _ORDER}
                if not any(d[c] for c in _ORDER):
                    continue

                rec = {
                    "product_name": name,
                    "opening_stock": d["OPENING"],
                    "purchase_stock": d["P.QTY"],
                    "purchase_free": d["P.FR"] + d["STN"],
                    "purchase_return": d["P.RTN"] + d["STNO"],
                    "sales_qty": d["S.QTY"],
                    "sales_free": d["S.FREE"],
                    "sales_return": d["S.RTN"],
                    "closing_stock": d["CL.STK"],
                    "closing_stock_value": d["CL.VALUE"],
                    "sales_value": d["S.VALUE"],
                }
                adj = d["ADJ"]
                if adj > 0:
                    rec["sales_return"] += adj
                elif adj < 0:
                    rec["purchase_return"] += -adj
                records.append(rec)

    return records
