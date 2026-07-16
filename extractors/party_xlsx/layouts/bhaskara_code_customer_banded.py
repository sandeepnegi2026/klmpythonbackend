"""
"Customer & Product" (BHASKARA MEDICAL AGENCIES / KLM) XLSX export.

Layout (band = CUSTOMER, detail rows = PRODUCTS) — a quantity-only party report
with NO value/amount column:

    BHASKARA MEDICAL AGENCIES
    D.NO:11-11-10/2,Vatturi Vari Street,VIJAYAWADA
    H & H Derma Customer & Product
    From 01/05/2026 To 27/05/2026
    Code | ProdName | Packing | Qty | Free                         <- header
    Code:B282   | Customer :AMARAVTHI MEDICAL&G&STORES,BHIMAVARAM  <- customer band
    KLCQC5      | COSMOQ MOISTURIZING CREAM | 50GM | 2 | 0         <- product line
    Code:G155   | Customer :MOHANA MEDICAL & GENERAL STORES,GUDIVADA
    KLCQSP      | COSMOQ SHAMPOO | 200ML | 1 | 0
    KLSEG       | SCARCOTE GEL   | 15GM  | 1 | 0

The customer sits in a *band* row whose col0 is "Code:<cust code>" and col1 is
"Customer :<name>,<city>" (the city glued after a comma). Every product line below
carries that customer until the next band. The generic ``tabular`` reader maps the
product columns (ProdName/Packing/Qty/Free) but there is no party column, so it never
binds ``party_name`` -> RED; and because the band's "Code:" col0 is not a "Customer :"
prefix, the shared ``customer_product_banded`` style-1 gate (which probes col0 only)
never fires.

There is NO value/amount column in this export — only Qty (sale qty) and Free — so
this layout emits ``qty`` + ``free_qty`` ONLY and never fabricates a value.

Gated on the exact compact header run ``codeprodnamepackingqtyfree`` (the unusual
"ProdName"/"Packing" cells make it unique to this family) PLUS a "Customer :" band in
col1 over a "Code:" col0, so it claims only this report; every other file stays on its
existing layout.
"""
import re

from extractors.party_xlsx.parse_common import cell_text, compact, is_subtotal, split_party_area

# The exact header run for this export. "ProdName" (one word) + "Packing" is unusual and,
# combined, occurs in no other corpus file -> a tight, unique gate.
_HEADER_TOKEN = "codeprodnamepackingqtyfree"

# The customer band: col1 = "Customer :<name>,<city>" (a leading col0 = "Code:<code>").
_CUSTOMER_BAND_RE = re.compile(r"^\s*customer\s*[:\-]\s*(.+)$", re.IGNORECASE)
# A "Code:<code>" band marker in col0 (the customer's account code).
_CODE_BAND_RE = re.compile(r"^\s*code\s*[:\-]\s*\S", re.IGNORECASE)


def _header_idx(rows):
    """Row index of the ``Code | ProdName | Packing | Qty | Free`` header, else None."""
    for idx, row in enumerate(rows[:15]):
        if compact(" ".join(cell_text(c) for c in row)) == _HEADER_TOKEN:
            return idx
    return None


def _customer_from_band(row):
    """Return (party_name, party_location) for a "Customer :<name>,<city>" band row.

    The "Customer :" text may sit in any cell of the band (col1 here, col0 defensively);
    the name/city are comma-split (name = first field, location = last field).
    """
    for cell in row:
        match = _CUSTOMER_BAND_RE.match(cell_text(cell))
        if match:
            return split_party_area(match.group(1).strip())
    return None


def detect(rows):
    if _header_idx(rows) is None:
        return False
    # Require at least one "Customer :" band whose row also carries a "Code:" col0 marker,
    # so a stray file that merely repeats the header tokens can never be claimed.
    header_idx = _header_idx(rows)
    for row in rows[header_idx + 1 : header_idx + 400]:
        if not row:
            continue
        first = cell_text(row[0])
        if _CODE_BAND_RE.match(first) and _customer_from_band(row):
            return True
    return False


def parse_bhaskara_code_customer_banded(rows):
    header_idx = _header_idx(rows)
    if header_idx is None:
        return [], {}

    records = []
    current_party = ""
    current_loc = ""
    for raw in rows[header_idx + 1 :]:
        if not raw:
            continue
        cells = [cell_text(c) for c in raw]
        first = cells[0]

        # Customer band: col0 == "Code:<code>", col1 == "Customer :<name>,<city>".
        if _CODE_BAND_RE.match(first):
            band = _customer_from_band(raw)
            if band:
                current_party, current_loc = band
                continue
            # A "Code:" row without a resolvable Customer band is noise -> skip.
            continue

        # Product line: col0=code, col1=ProdName, col2=Packing, col3=Qty, col4=Free.
        product = cells[1] if len(cells) > 1 else ""
        if not product or is_subtotal(product) or not re.search(r"[A-Za-z0-9]", product):
            # Skips blank rows, subtotals, and stray control-char junk (e.g. a lone
            # "_x001B_P" end-of-report artifact sitting alone in col0).
            continue
        if not current_party:
            continue

        record = {
            "hsn_code": first,  # the product/item code (Code column)
            "product_name": product,
            "pack": cells[2] if len(cells) > 2 else "",
            # POSITIONAL quantity split — Qty is the sale quantity, Free the free-goods
            # count. There is NO value column, so amount is intentionally left unset.
            "qty": cells[3] if len(cells) > 3 else "",
            "free_qty": cells[4] if len(cells) > 4 else "",
            "party_name": current_party,
        }
        if current_loc:
            record["party_location"] = current_loc
        records.append(record)

    detected = {
        "Code": "hsn_code",
        "ProdName": "product_name",
        "Packing": "pack",
        "Qty": "qty",
        "Free": "free_qty",
    }
    return records, detected
