"""KLM / R K PHARMA "Company Product Wise Sales" — flat bill-detail XLSX export.

R.K. PHARMA "klm cosmo party wise.xlsx" (Marg/KLM export). A single flat header row
with per-invoice detail lines, interleaved with ``COMPANY NAME :`` and ``CUST NAME :``
band rows and ``GROUP TOTAL`` / ``NET TOTAL`` footer rows::

    Company Name:R K PHARMA
    Company Address:KURNOOL,518002
    Report Name:Company Product Wise Sales
    Report Heading: Company Code = KLM COSMO DIVISION, InvDate Between ...
    NAME | INVOICE NUMBER | INV DATE | BATCH | QUANTITY | FREE QTY | AMOUNT | PRODUCT NAME  <- header
    COMPANY NAME : KLM COSMO DIVISION                                  <- division band (col0 only)
    CUST NAME : MOTHER MEDICAL AND FANCY STORES                        <- party band (col0 only, CLEAN name)
    MOTHER MEDICAL...STORES-IN PREMISES OF...-K.G.ROAD;ATMAKUR | ER012606 | 2026-06-27 | CN506 | 5 | 0 | 4813.55 | IMXIA XL SERUM 60ML-60ML  <- detail line
    GROUP TOTAL MOTHER MEDICAL AND FANCY STORES | | | | 5 | 0 | 4813.55                    <- subtotal (skip)
    GROUP TOTAL KLM COSMO DIVISION              | | | | 5 | 0 | 4813.55                    <- subtotal (skip)
    NET TOTAL                                   | | | | 5 | 0 | 4813.55                    <- footer (skip)

The generic ``tabular`` reader maps the numeric columns but binds the NAME column to
product_name (there is a separate PRODUCT NAME column too), so the party is never
extracted cleanly (RED MISSING_REQUIRED_FIELD:party_name). This reader binds columns by
their EXACT header cells and carries the CLEAN party name from the ``CUST NAME :`` band
onto each detail line below it.

MAPPING (exact header text -> canonical; qty/value kept SEPARATE, never derived):
    PRODUCT NAME    -> product_name   (strip trailing "-<pack>" duplicate suffix kept as-is)
    CUST NAME band  -> party_name     (clean trade name from the band, NOT the glued NAME col)
    NAME (detail)   -> party_location (town = text after last ';' in the glued NAME cell)
    COMPANY NAME band -> division
    INVOICE NUMBER  -> invoice_number
    INV DATE        -> invoice_date
    BATCH           -> batch_no
    QUANTITY        -> qty
    FREE QTY        -> free_qty        (scheme/free)
    AMOUNT          -> amount

RECONCILE (party route — no stock identity): the per-line AMOUNT is the printed gross
value; the ``GROUP TOTAL`` / ``NET TOTAL`` footer rows equal the running QTY-sum and
AMOUNT-sum of the detail lines above them (this file: 1 line, qty 5 / free 0 / amount
4813.55 == both GROUP TOTAL rows and NET TOTAL). qty is taken from QUANTITY only.

GATE: the compact contiguous header run
    "nameinvoicenumberinvdatebatchquantityfreeqtyamountproductname"
is unique to this flat "Company Product Wise Sales" export (no other corpus format
carries the INVOICE NUMBER / INV DATE / BATCH / QUANTITY / FREE QTY / AMOUNT / PRODUCT
NAME single-header run), so it can only ever claim this report.
"""
import re

from extractors.party_xlsx.parse_common import cell_text, compact

# Long contiguous run of the exact flat header cells; specific enough that no other export
# collides.
_HEADER_TOKEN = "nameinvoicenumberinvdatebatchquantityfreeqtyamountproductname"

# Band rows carried in col0 only.
_CUST_RE = re.compile(r"^\s*CUST\s*NAME\s*:\s*(.+)$", re.IGNORECASE)
_COMPANY_RE = re.compile(r"^\s*COMPANY\s*NAME\s*:\s*(.+)$", re.IGNORECASE)
# Footer / subtotal rows (GROUP TOTAL ..., NET TOTAL, GRAND TOTAL).
_TOTAL_RE = re.compile(r"^\s*(?:GROUP\s+TOTAL|NET\s+TOTAL|GRAND\s+TOTAL|TOTAL)\b", re.IGNORECASE)


def _header_idx(rows):
    for i, row in enumerate(rows[:25]):
        if _HEADER_TOKEN in compact(" ".join(cell_text(c) for c in row)):
            return i
    return None


def detect(rows):
    return _header_idx(rows) is not None


def _num(tok):
    tok = (tok or "").strip().replace(",", "")
    if not tok or tok == "-":
        return "0"
    return tok


def _location_from_name(name):
    """The glued NAME detail cell is "<TRADE NAME>-<addr>-<addr>;<TOWN>".

    The town is the text after the last ';' (falls back to text after the last '-').
    Only used for party_location; the clean party_name comes from the CUST NAME band.
    """
    raw = name.strip()
    if ";" in raw:
        town = raw.rsplit(";", 1)[-1].strip()
        if town:
            return town
    return ""


def parse_company_product_wise_sales_custband(rows):
    detected = {
        "PRODUCT NAME": "product_name",
        "CUST NAME": "party_name",
        "COMPANY NAME": "division",
        "NAME": "party_location",
        "INVOICE NUMBER": "invoice_number",
        "INV DATE": "invoice_date",
        "BATCH": "batch_no",
        "QUANTITY": "qty",
        "FREE QTY": "free_qty",
        "AMOUNT": "amount",
    }
    hidx = _header_idx(rows)
    if hidx is None:
        return [], detected

    header = [cell_text(c).strip() for c in rows[hidx]]

    def col(name):
        for i, h in enumerate(header):
            if h.strip().lower() == name.lower():
                return i
        return None

    ci = {
        "name": col("NAME"),
        "invoice": col("INVOICE NUMBER"),
        "date": col("INV DATE"),
        "batch": col("BATCH"),
        "qty": col("QUANTITY"),
        "free": col("FREE QTY"),
        "amount": col("AMOUNT"),
        "product": col("PRODUCT NAME"),
    }

    def at(cells, key):
        i = ci.get(key)
        return cells[i].strip() if (i is not None and i < len(cells)) else ""

    records = []
    current_party = current_div = ""
    for raw in rows[hidx + 1:]:
        cells = [cell_text(c) for c in raw]
        if not any(c.strip() for c in cells):
            continue
        c0 = cells[0].strip() if cells else ""

        m = _CUST_RE.match(c0)
        if m:
            current_party = " ".join(m.group(1).split())
            continue
        m = _COMPANY_RE.match(c0)
        if m:
            current_div = " ".join(m.group(1).split())
            continue
        # Footer / subtotal rows sit in col0 with a TOTAL keyword.
        if _TOTAL_RE.match(c0):
            continue

        product = at(cells, "product")
        if not product:
            continue
        if not current_party:
            continue

        rec = {
            "division": current_div,
            "party_name": current_party,
            "product_name": product,
            "batch_no": at(cells, "batch"),
            "invoice_number": at(cells, "invoice"),
            "invoice_date": at(cells, "date"),
            "qty": _num(at(cells, "qty")),
            "free_qty": _num(at(cells, "free")),
            "amount": _num(at(cells, "amount")),
        }
        loc = _location_from_name(at(cells, "name"))
        if loc:
            rec["party_location"] = loc
        records.append(rec)

    return records, detected
