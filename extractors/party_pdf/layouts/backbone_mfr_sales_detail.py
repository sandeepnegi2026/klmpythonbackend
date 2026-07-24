"""BackBone "MFR SALES DETAIL REPORT" — party-wise billwise sales (PURANI
HOSPITAL SUPPLIES PVT LTD).

Vendor / ERP : BackBone ("Powered By BackBone"), HTML-print-to-PDF export.
Title        : "MFR SALES DETAIL REPORT (dd-mm-yyyy To dd-mm-yyyy)".
Format       : bordered lattice table, one manufacturer/division per file
               (05-KLM COSMO, KLM DERMA, ...). Every product line is a lattice
               ROW whose Product Name / BillNo-Date / Customer Name / City /
               Expiry cells wrap over several physical text lines.

Column header (wrapped over 3 physical lines):
    Product Name | BillNo/Date | Customer Name | City | Batch | Expiry |
    Qty | FreeQty | Rpl Qty | PTR | Total Sales

Column map (11 lattice columns):
    [0] Product Name  -> product_name          (drop embedded newline)
    [1] BillNo/Date   -> invoice_number + invoice_date  ("<no>/<dd>-<mm>-<yyyy>")
    [2] Customer Name -> party_name            (strip trailing "( code )")
    [3] City          -> party_location
    [4] Batch         -> batch_no
    [5] Expiry        -> expiry                ("<Mon>-<yyyy>")
    [6] Qty           -> qty       (negative row = sales return)
    [7] FreeQty       -> free_qty
    [8] Rpl Qty       -> raw_rpl_qty  (kept raw; excluded from reconcile)
    [9] PTR           -> rate
    [10] Total Sales  -> amount

Reconcile equation (per file, page-1 printed banner):
    sum(qty)   == "Total NetSales QTY: <N>"
    sum(amount)== "Total NetSales : <V>"
(Net = Sales + SalesReturn; a return row prints qty and amount as negatives.)

Extraction is via pdfplumber's lattice extract_tables (clean per-cell columns).
A handful of *single-line* rows — where the whole record renders on one text
line and its customer cell straddles a page break — are DROPPED by the lattice
extractor (they leave an orphan "( <code> )" fragment on the next page). Those
are recovered from the page text via a trailing "<qty> <free> <rpl> <ptr>
<total>" band anchored on the "<billno>/<dd>-" token, keyed on bill number so a
row already captured by the table is never double-counted. With the recovery,
all six reference files reconcile exactly to the printed Net totals.

Positional parser: needs file_bytes to re-open the PDF for extract_tables; the
flat text layer interleaves the wrapped cells and cannot be column-split.
"""

import io
import re

import pdfplumber

H = ['Product Name', 'Bill No', 'Bill Date', 'Party Name', 'City',
     'Batch', 'Expiry', 'Qty', 'Free', 'Rate', 'Amount']

_HDR0 = 'Product Name'

# "<billno>/<dd>-<mm>-<yyyy>"  (the "-<mm>-<yyyy>" wraps to the 2nd cell line)
_BILL = re.compile(r'^\s*(\d+)\s*/\s*(\d{2}\s*-\s*\d{2}\s*-\s*\d{4})')

# trailing "( 5537 )" customer code fragment
_CODE_TAIL = re.compile(r'\s*\(\s*\d+\s*\)\s*$')

# single-line row: "<PRODUCT...> <billno>/<dd>- ... <qty> <free> <rpl> <ptr> <total>"
_LINE = re.compile(
    r'^(?P<prod>.*?)\s+(?P<bill>\d{3,})/(?P<dd>\d{2})-\s+'
    r'(?P<mid>.*?)\s+'
    r'(?P<qty>-?\d+)\s+(?P<free>\d+)\s+(?P<rpl>\d+)\s+'
    r'(?P<ptr>-?\d+(?:\.\d+)?)\s+(?P<tot>-?\d+\.\d+)\s*$'
)

# On a straddling single-line row the middle text reads
# "<CUSTOMER..> <BATCH> <Mon>" — the expiry YEAR has wrapped off-line, so only
# the 3-letter month remains as the trailing token.
_MON = re.compile(r'\s+([A-Za-z]{3})-?\s*$')


def _num(x):
    x = (x or '').strip().replace(',', '')
    if x in ('', '-'):
        return None
    try:
        return float(x)
    except ValueError:
        return None


def _clean(cell):
    return (cell or '').replace('\n', ' ').strip()


def _split_bill(cell):
    """BillNo/Date cell -> (invoice_number, invoice_date). The cell reads
    "<no>/<dd>-<mm>-<yyyy>" (the date wraps but the newline collapses to space).
    """
    s = _clean(cell)
    m = _BILL.match(s)
    if not m:
        return s, ''
    bill = m.group(1)
    date = re.sub(r'\s+', '', m.group(2))  # dd-mm-yyyy
    return bill, date


def _split_party(cell):
    """Customer Name cell -> party_name with the trailing "( code )" peeled."""
    s = _clean(cell)
    s = _CODE_TAIL.sub('', s).strip()
    return s.rstrip(' -')


def parse_backbone_mfr_sales_detail(text, file_bytes=None):
    if not file_bytes:
        return H, []

    rows = []
    seen_bills = set()

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        pages = list(pdf.pages)

        # --- 1) lattice table rows (clean columns) --------------------------
        for pg in pages:
            for tb in pg.extract_tables():
                for r in tb:
                    if not r or len(r) < 11:
                        continue
                    if _clean(r[0]) == _HDR0:
                        continue
                    qty = _num(r[6])
                    tot = _num(r[10])
                    if qty is None and tot is None:
                        # continuation fragment (orphan customer-code cell) — the
                        # numbered row it belongs to is recovered from text below.
                        continue
                    bill, date = _split_bill(r[1])
                    if bill:
                        seen_bills.add(bill)
                    rows.append([
                        _clean(r[0]),                         # product
                        bill, date,                           # bill no / date
                        _split_party(r[2]),                   # party
                        _clean(r[3]),                         # city
                        _clean(r[4]),                         # batch
                        re.sub(r'\s+', ' ', _clean(r[5])),    # expiry
                        r[6] if qty is not None else '0',     # qty
                        r[7] if _num(r[7]) is not None else '0',   # free
                        _clean(r[9]),                         # ptr -> rate
                        (r[10] or '0').replace(',', '').strip(),   # total -> amount
                    ])

        # --- 2) recover single-line rows the lattice extractor dropped ------
        # (their customer cell straddles a page boundary). Keyed on bill number
        # so a row already captured above is never re-emitted.
        for pg in pages:
            for ln in (pg.extract_text() or '').split('\n'):
                s = ln.strip()
                if not s:
                    continue
                m = _LINE.match(s)
                if not m:
                    continue
                bill = m.group('bill')
                if bill in seen_bills:
                    continue
                seen_bills.add(bill)
                prod = m.group('prod').strip()
                mid = m.group('mid').strip()
                # peel the trailing "( code )" fragment from the customer text
                mid = _CODE_TAIL.sub('', mid).strip()
                # peel the trailing expiry month (year has wrapped off-line)
                expiry = ''
                em = _MON.search(mid)
                if em:
                    expiry = em.group(1)
                    mid = mid[:em.start()].strip()
                # the now-last token carrying a digit is the batch; rest is party
                batch = ''
                toks = mid.split()
                if toks and re.search(r'\d', toks[-1]):
                    batch = toks[-1]
                    toks = toks[:-1]
                party = _split_party(' '.join(toks))
                rows.append([
                    prod,
                    bill, '',
                    party, '',
                    batch, expiry,
                    m.group('qty'),
                    m.group('free'),
                    m.group('ptr'),
                    m.group('tot').replace(',', ''),
                ])

    return H, rows
