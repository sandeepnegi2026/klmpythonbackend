"""KLM 'Stock And Sale Report(Month)' — Prv2/Repl dialect (SUCCESS PHARMAA & VACCINE).

Sibling of the KLM per-division "Stock And Sale(s) Report(Month)" family
(klm_stock_sales_month / _repq / _rcpt / _urate), a distinct column vocabulary that
carries a leading item CODE column, TWO prior-month sale columns, and Repl/Adj.
Header (single row, the value columns are two-word 'Closing St' / 'Stock Valu'):

  Produc | ProductName | Packi | OpStk | Rcpt | Prv2.S | Prv.Sa | Sales | Free |
  Repl | Adj | SalesValue | Closing St | Stock Valu

Zero-movement cells print BLANK and the numbers are right-aligned, so we read word
x-positions with pdfplumber and bucket each value into the column whose header
right-edge (x1) it aligns to. Qty columns are integers; the two VALUE columns
(SalesValue, Stock Valu) are the only decimals, so they are bucketed among the two
value anchors by x1 (a row may carry only one of them). Every data row begins with a
4-6 digit item CODE (x0 at the left margin) — requiring it discards the division
band rows ('1481 KLM PHARMA') and the 'Op.Stk.Val: ... Sales ...' footer band (whose
rupee cells would otherwise inflate the value totals).

Layout quirk (shared with the _rcpt/_urate siblings): the ENTIRE report renders on
every physical page, so we parse page 0 ONLY. Verified on all 7 SUCCESS division
books: qty reconciles 100% and every column sum matches the printed 'Sub Total' row
exactly (OpStk / Rcpt / Sales / Closing qty AND SalesValue / Stock-value totals):

  Closing = OpStk + Rcpt - Sales - Free (+/- Adj)

Prv2.S / Prv.Sa are prior-month sales (informational) and Repl is a replacement
figure outside the stock identity (footer prints a separate 'Repl Value:'); both are
dropped. Field mapping: OpStk->opening_stock, Rcpt->purchase_stock, Sales->sales_qty,
Free->sales_free, Adj->signed(sales_return/purchase_return), Closing St->closing_stock,
Stock Valu->closing_stock_value, SalesValue->sales_value.

Gate (compact): 'stockandsalereport(month)' + 'prv2.sprv.sa' + 'repladjsalesvalue'
(the two prev-month abbreviations + Repl/Adj/SalesValue run are unique to this export).
"""
import io
import re

_NUM = re.compile(r"^-?\d[\d,]*\.?\d*$")
_CODE = re.compile(r"^\d{3,6}$")
_INT_COLS = ["OpStk", "Rcpt", "Prv2.S", "Prv.Sa", "Sales", "Free", "Repl", "Adj", "ClosingSt"]


def _val(t):
    try:
        return float(t.replace(",", ""))
    except ValueError:
        return None


def _anchors(row):
    txt = {w["text"]: w for w in row}
    if not ("OpStk" in txt and "Rcpt" in txt and "SalesValue" in txt and "St" in txt and "Valu" in txt):
        return None
    a = {}
    for key, tok in [("OpStk", "OpStk"), ("Rcpt", "Rcpt"), ("Prv2.S", "Prv2.S"),
                     ("Prv.Sa", "Prv.Sa"), ("Sales", "Sales"), ("Free", "Free"),
                     ("Repl", "Repl"), ("Adj", "Adj"), ("ClosingSt", "St"),
                     ("SalesValue", "SalesValue"), ("StockValu", "Valu")]:
        if tok in txt:
            a[key] = txt[tok]["x1"]
    return a, txt["OpStk"]["x0"] - 4


def parse_klm_stock_sales_month_prv2(text, file_bytes=None):
    if not file_bytes:
        return []
    import pdfplumber

    records = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        page = pdf.pages[0]
        words = page.extract_words()
        by_top = {}
        for w in words:
            by_top.setdefault(round(w["top"]), []).append(w)

        anchors = name_cut = None
        int_keys = int_x = None
        for top in sorted(by_top):
            row = sorted(by_top[top], key=lambda w: w["x0"])
            found = _anchors(row)
            if found:
                anchors, name_cut = found
                int_keys = [k for k in _INT_COLS if k in anchors]
                int_x = [anchors[k] for k in int_keys]
                continue
            if anchors is None:
                continue

            code = next((w["text"] for w in row if w["x1"] <= 30), "")
            if not _CODE.match(code):
                continue
            nums = [w for w in row if _NUM.match(w["text"]) and (w["x0"] + w["x1"]) / 2 > name_cut]
            name = " ".join(w["text"] for w in row if 30 < w["x1"] <= name_cut).strip()
            if not name or not nums:
                continue

            col = {}
            for w in nums:
                if "." in w["text"]:
                    key = ("SalesValue" if abs(w["x1"] - anchors["SalesValue"])
                           <= abs(w["x1"] - anchors["StockValu"]) else "StockValu")
                    col.setdefault(key, _val(w["text"]))
                else:
                    bi = min(range(len(int_x)), key=lambda i: abs(int_x[i] - w["x1"]))
                    if abs(int_x[bi] - w["x1"]) < 8:
                        col.setdefault(int_keys[bi], _val(w["text"]))

            op = col.get("OpStk") or 0.0
            rcpt = col.get("Rcpt") or 0.0
            sale = col.get("Sales") or 0.0
            free = col.get("Free") or 0.0
            cls = col.get("ClosingSt")
            if cls is None and not any([op, rcpt, sale]):
                continue

            rec = {
                "product_name": name,
                "opening_stock": op,
                "purchase_stock": rcpt,
                "sales_qty": sale,
                "sales_free": free,
                "closing_stock": cls if cls is not None else 0.0,
                "closing_stock_value": col.get("StockValu") or 0.0,
                "sales_value": col.get("SalesValue") or 0.0,
            }
            adj = col.get("Adj") or 0.0
            if adj > 0:
                rec["sales_return"] = adj
            elif adj < 0:
                rec["purchase_return"] = -adj
            records.append(rec)

    return records
