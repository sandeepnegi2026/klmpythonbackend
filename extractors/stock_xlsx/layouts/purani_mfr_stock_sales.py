"""PURANI HOSPITAL SUPPLIES LTD — "MFR Stock and Sales Report" (HTML-in-.xls).

Vendor : PURANI HOSPITAL SUPPLIES LTD (download.xls / klm.xls)
Format : a 417 KB HTML document masquerading as an .xls (starts '<div id="hdTableview1">').
         workbook_kind() routes it to the ".html" branch. The generic html_stock parser
         keys on `<td class="text-start">` which never appears here (all cells are
         class-less), so it extracts 0 rows.

Shape  : Per division ("KLM <X> DIVISION - MFR Stock and Sales Report as on - dd-mm-yyyy")
         the document carries the current-month product table PLUS 1-2 prior-month blocks
         (per-division "Total Value" summaries chain: this-month Opening value == last
         month's Closing value). Each product table has 18 columns:

           S.No | Particulars | Pack | O.St | Pur | Free | PRtn | MBMon | LMon | Mon |
           C.St | P.Qty | E.PO | Rate | Sales | Stock | Box | P.Dt

         Column map (canonical):
           Particulars -> product_name
           Pack        -> pack
           O.St [3]    -> opening_stock
           Pur  [4]    -> purchase_stock
           Free [5]    -> purchase_free
           PRtn [6]    -> purchase_return
           Mon  [9]    -> sales_qty            (current-month sales quantity)
           C.St [10]   -> closing_stock
           Rate [13]   -> rate
           Sales[14]   -> sales_value          (= Mon x Rate)
           Stock[15]   -> closing_stock_value
         MBMon/LMon (prior-month qty), P.Qty/E.PO/Box/P.Dt are ignored.

Reconcile equation (holds row-wise on 100% of data rows):
           C.St = O.St + Pur + Free - PRtn - Mon
         e.g. ZYCOZOL XL: 11 + 15 + 0 - 0 - 21 = 5 = C.St ;  Sales 5250 = Mon 21 x Rate 250.

De-dup  : Only the FIRST 18-col product table encountered under each fresh "KLM <X>
          DIVISION" heading (in DOM order) is the current-month block. Subsequent 18-col
          tables for the same division are prior-month blocks and are skipped, so products
          are never double-counted. The ancillary "Total Value" (4-row), "Stock Received
          During the Month" and "Pending Cliam(s)" tables are non-18-col and ignored.
          Division tag is the nearest preceding heading.
"""

import re
from html.parser import HTMLParser

# 18-column current-month header, by exact leading tokens.
_HEADER = ["S.No", "Particulars", "Pack", "O.St", "Pur", "Free", "PRtn"]

_DIV_RE = re.compile(r"(KLM\s+[A-Z0-9]+)\s+DIVISION", re.I)


class _MfrHtmlParser(HTMLParser):
    """Collect, in document order, division heading events and full <table> grids.

    Emits a flat ``events`` list of ("head", division_text) and ("table", rows) tuples so
    the caller can bind each product table to the division heading that precedes it.
    """

    def __init__(self):
        super().__init__()
        self.events = []
        self._table = None
        self._row = None
        self._cell = None
        self._buf = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
            self._buf = self._cell

    def handle_endtag(self, tag):
        if tag == "table" and self._table is not None:
            self.events.append(("table", self._table))
            self._table = None
        elif tag == "tr" and self._row is not None:
            self._table.append(self._row)
            self._row = None
        elif tag in ("td", "th") and self._cell is not None:
            self._row.append("".join(self._cell).strip())
            self._cell = None
            self._buf = None

    def handle_data(self, data):
        if self._buf is not None:
            self._buf.append(data)
        else:
            # Free-standing text (division banner) between tables.
            text = " ".join(data.split())
            if text and "DIVISION" in text.upper() and "KLM" in text.upper():
                self.events.append(("head", text))


def _num(value):
    text = str(value).replace(",", "").strip()
    # Blank cells and the ERP's literal "null" placeholder both mean zero movement.
    if text.lower() in ("", "-", "--", "-----", "null"):
        return 0.0
    try:
        return float(text)
    except ValueError:
        return None


def _is_product_table(rows):
    return bool(rows) and len(rows[0]) == 18 and rows[0][:7] == _HEADER


def parse_purani_mfr_stock_sales(file_bytes):
    text = file_bytes.decode("utf-8-sig", errors="replace")
    parser = _MfrHtmlParser()
    parser.feed(text)

    records = []
    current_div = None
    div_taken = set()  # divisions whose current-month product table is already captured

    for kind, payload in parser.events:
        if kind == "head":
            match = _DIV_RE.search(payload.upper())
            current_div = match.group(1) if match else payload
            continue

        table = payload
        if not _is_product_table(table):
            continue
        # Only the first product table under a division heading is current-month.
        if current_div in div_taken:
            continue
        div_taken.add(current_div)

        for row in table[1:]:
            if len(row) != 18 or not str(row[0]).strip().isdigit():
                continue  # header echoes, blank spacers, non-data rows
            opening = _num(row[3])
            purchase = _num(row[4])
            pur_free = _num(row[5])
            pur_ret = _num(row[6])
            sales = _num(row[9])
            closing = _num(row[10])
            if opening is None or purchase is None or closing is None:
                continue
            rec = {
                "product_name": str(row[1]).strip(),
                "pack": str(row[2]).strip(),
                "opening_stock": opening,
                "purchase_stock": purchase,
                "purchase_free": pur_free or 0.0,
                "purchase_return": pur_ret or 0.0,
                "sales_qty": sales or 0.0,
                "closing_stock": closing,
                "rate": _num(row[13]) or 0.0,
                "sales_value": _num(row[14]) or 0.0,
                "closing_stock_value": _num(row[15]) or 0.0,
            }
            if current_div:
                rec["division"] = current_div
            records.append(rec)

    detected = {
        "Particulars": "product_name",
        "Pack": "pack",
        "O.St": "opening_stock",
        "Pur": "purchase_stock",
        "Free": "purchase_free",
        "PRtn": "purchase_return",
        "Mon": "sales_qty",
        "C.St": "closing_stock",
        "Rate": "rate",
        "Sales": "sales_value",
        "Stock": "closing_stock_value",
    }
    return records, detected
