"""SwilERP party billwise report shipped as HTML-in-.xls (e.g. PURANI HOSPITAL SUPPLIES).

Vendor  : PURANI HOSPITAL SUPPLIES LTD ("Party report/download _1_.xls").
Format  : a SwilERP web export written as an HTML document but saved with a .xls
          extension (starts '<div id="txtmanuheader...">'). The ordinary party_xlsx
          reader hands it to pandas/xlrd, gets 0 rows / empty raw_text, and the file
          triages RED (SCANNED_OR_EMPTY). This mirrors the STOCK route's twin handler
          (extractors/stock_xlsx/layouts/purani_mfr_stock_sales.py) which already parses
          the vendor's HTML-in-.xls stock export via stdlib html.parser.

Shape   : a single <table> whose header row is exactly

            Product Name | BillNo/Date | Customer Name | City | Batch | Expiry |
            Qty | FreeQty | Rpl Qty | PTR | Total Sales

          and 77 product/bill data rows below it. Column map (canonical party fields):

            Product Name   -> product_name
            BillNo/Date    -> invoice_number + invoice_date  (split on '/', date is
                              DD-MM-YYYY, normalised via core.dates.to_iso_date)
            Customer Name  -> party_name  (trailing ' ( 1234 )' party code stripped)
            City           -> party_location
            Batch          -> batch_no
            Expiry         -> expiry
            Qty            -> qty
            FreeQty        -> free_qty
            PTR            -> rate  (also stashed as ptr)
            Total Sales    -> amount
          Rpl Qty (replacement qty) is not a canonical party field and is ignored.

Gate    : detect() requires BOTH the HTML content AND the SwilERP party-billwise header
          (a header row carrying 'Customer Name' AND 'BillNo' AND 'Total Sales'), so this
          can only ever catch this SwilERP party-HTML export, never a real .xlsx/.xls.
"""
import re
from html.parser import HTMLParser

from core.dates import to_iso_date

# Trailing SwilERP party-code tag on a customer name, e.g. "VAARTHAA PHARMACY(...) ( 1797 )".
_PARTY_CODE_RE = re.compile(r"\s*\(\s*\d+\s*\)\s*$")

# HTML magic markers at the very start of the document.
_HTML_MARKERS = (b"<div", b"<html", b"<table", b"<!doctype")

# Header columns that uniquely identify a SwilERP party-billwise HTML table.
_REQUIRED_HDR = ("customer name", "billno", "total sales")


def is_html(file_bytes):
    """True when the raw bytes begin with an HTML document (case-insensitive)."""
    head = file_bytes[:4096].lstrip()[:64].lower()
    return any(head.startswith(marker) for marker in _HTML_MARKERS)


class _TableParser(HTMLParser):
    """Collect every <table> as a list of rows, each row a list of cell strings."""

    def __init__(self):
        super().__init__()
        self.tables = []
        self._table = None
        self._row = None
        self._cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag):
        if tag == "table" and self._table is not None:
            self.tables.append(self._table)
            self._table = None
        elif tag == "tr" and self._row is not None:
            self._table.append(self._row)
            self._row = None
        elif tag in ("td", "th") and self._cell is not None:
            self._row.append("".join(self._cell).strip())
            self._cell = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def _html_tables(file_bytes):
    parser = _TableParser()
    parser.feed(file_bytes.decode("utf-8-sig", errors="replace"))
    return parser.tables


def _is_party_header(row):
    joined = " ".join(str(cell) for cell in row).lower()
    return all(token in joined for token in _REQUIRED_HDR)


def detect(file_bytes):
    """Gate: HTML content AND a SwilERP party-billwise header row present."""
    if not is_html(file_bytes):
        return False
    for table in _html_tables(file_bytes):
        if table and _is_party_header(table[0]):
            return True
    return False


def _clean_party_name(name):
    return _PARTY_CODE_RE.sub("", str(name)).strip()


def _split_bill(cell):
    """'12933/01-06-2026' -> ('12933', '2026-06-01'). Only the FIRST '/' splits number
    from date, so a date with internal slashes stays intact on the date side."""
    text = str(cell).strip()
    if "/" not in text:
        return text, ""
    number, _, date = text.partition("/")
    iso = to_iso_date(date.strip())
    return number.strip(), (iso if iso else date.strip())


def parse_swil_html_billwise(file_bytes):
    tables = _html_tables(file_bytes)
    header, body = None, []
    for table in tables:
        if table and _is_party_header(table[0]):
            header, body = table[0], table[1:]
            break
    if header is None:
        return [], {}

    # Map the canonical header column -> index by exact position of the known labels.
    norm = [str(cell).strip().lower() for cell in header]

    def idx(label):
        label = label.lower()
        return norm.index(label) if label in norm else None

    i_product = idx("product name")
    i_bill = idx("billno/date")
    i_customer = idx("customer name")
    i_city = idx("city")
    i_batch = idx("batch")
    i_expiry = idx("expiry")
    i_qty = idx("qty")
    i_free = idx("freeqty")
    i_ptr = idx("ptr")
    i_amount = idx("total sales")

    def at(cells, i):
        return cells[i].strip() if (i is not None and i < len(cells)) else ""

    records = []
    for cells in body:
        cells = [str(c) for c in cells]
        product = at(cells, i_product)
        party = _clean_party_name(at(cells, i_customer))
        if not product or not party:
            continue  # header echoes / blank spacer rows carry neither
        number, date = _split_bill(at(cells, i_bill))
        rate = at(cells, i_ptr)
        record = {
            "product_name": product,
            "party_name": party,
            "party_location": at(cells, i_city),
            "invoice_number": number,
            "invoice_date": date,
            "batch_no": at(cells, i_batch),
            "expiry": at(cells, i_expiry),
            "qty": at(cells, i_qty),
            "free_qty": at(cells, i_free),
            "rate": rate,
            "ptr": rate,
            "amount": at(cells, i_amount),
        }
        records.append(record)

    detected = {
        "Product Name": "product_name",
        "Customer Name": "party_name",
        "City": "party_location",
        "BillNo/Date": "invoice_number+invoice_date",
        "Batch": "batch_no",
        "Expiry": "expiry",
        "Qty": "qty",
        "FreeQty": "free_qty",
        "PTR": "rate",
        "Total Sales": "amount",
    }
    return records, detected
