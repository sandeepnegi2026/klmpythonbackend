"""
"Customer-Product wise Sales" — SwilERP Excel export (M.G. DISTRIBUTORS / KLM).

A three-column customer-banded sales summary::

    M.G. DISTRIBUTORS                                     <- vendor header (skip)
    15,PARSHVANATH DAVA BAZAR,UDAIPUR - 313001            <- vendor address (skip)
    Customer-Product wise Sales (From 01/05/2026 ...)     <- title (gate token)
    Product Name | Qty. | Value                           <- header (3 cells)
    L00221-A TO Z MEDICAL STORE,UDAIPUR                   <- CUSTOMER band (col0 only)
    NEVLON 100GM CREAM. | 1 | 192.54                      <- product line
    TOTAL |  | 192.54                                     <- per-party subtotal (skip)
    L001495-AARSH MEDI SALES,UDAIPUR                      <- next CUSTOMER band
    TYROLITE-15GM CREAM. | 20 | 7566.2
    ...
    GRAND TOTAL |  | 97974.82                             <- grand total (skip)
    *****                                                 <- footer (skip)
    Powered By SwilERP for Retail, Distribution & ...     <- footer (skip)

The customer sits in a bare ``CODE-NAME,CITY`` band row (its Qty/Value cells blank),
introducing the product lines below it. The header is only THREE columns
(``Product Name | Qty. | Value``), so the shared ``customer_product_banded`` reader
never fires (its ``detect_header_row(min_matches=4)`` needs 4 mapped columns), the file
falls through to the generic ``tabular`` reader which maps product/qty/value fine but
NEVER binds a ``party_name`` (there is no party column) -> RED
(MISSING_REQUIRED_FIELD:party_name).

This layout carries the current band's customer (and its trailing city) down onto every
product row until the next band. qty and value are read from their OWN columns (Qty. and
Value) — value is never derived from qty. Reconciles: the product Value column sums to the
printed GRAND TOTAL exactly (97974.82).

Gate token (compact, lowercased, spaces stripped): ``customerproductwisesales`` in the
title block PLUS the exact 3-cell header ``productnameqtyvalue``. Both required, so the
"Product-Customer Wise Sales" sibling (its own layout, header ``customerstationqtysalesvalue``)
and every other export stay untouched.
"""
import re

from extractors.party_xlsx.parse_common import cell_text, compact

_TITLE = "customerproductwisesales"
_HEADER = "productnameqtyvalue"

# A "CODE-NAME,CITY" customer band: a code token (letters/digits/dot/hyphen, e.g. "L00221",
# "L001495", "L0055"), a hyphen, then a NAME starting with a letter, optionally ",CITY,(phone)".
# The code is lazy so an internal hyphen in the name does not end the code prematurely; the name
# must start with a letter so a product line ("NEVLON 100GM CREAM.") never matches (it has no
# leading "code-").
_CODE_NAME_BAND_RE = re.compile(r"^\s*[A-Za-z0-9][A-Za-z0-9.\-]*?\s*-\s*([A-Za-z].*)$")

# Per-party / grand subtotal rows: col0 is exactly TOTAL / GRAND TOTAL (Qty blank, Value filled).
_SUBTOTAL_LABELS = {"total", "grand total"}


def _header_idx(rows):
    for idx, row in enumerate(rows[:15]):
        if compact(" ".join(cell_text(c) for c in row)) == _HEADER:
            return idx
    return None


def detect(rows):
    if _header_idx(rows) is None:
        return False
    head = compact(" ".join(" ".join(cell_text(c) for c in r) for r in rows[:8]))
    return _TITLE in head


def _split_band(text):
    """'L001495-AARSH MEDI SALES,UDAIPUR' -> ('AARSH MEDI SALES', 'UDAIPUR'), else None.

    The name is the text after 'code-' up to the first comma; the city is the next
    comma-field with any '(phone)' tail dropped. Requires >=3 letters in the name so a
    stray code row can never become a phantom party.
    """
    match = _CODE_NAME_BAND_RE.match(text)
    if not match:
        return None
    body = match.group(1)
    name = body.split(",")[0].strip()
    if len(re.findall(r"[A-Za-z]", name)) < 3:
        return None
    rest = body.split(",")[1:]
    loc = re.sub(r"\(.*", "", rest[0]).strip() if rest else ""
    return name, loc


def parse_r15_customer_product_wise_sales_swil(rows):
    header_idx = _header_idx(rows)
    if header_idx is None:
        return [], {}

    records = []
    current_party = ""
    current_loc = ""
    for raw in rows[header_idx + 1:]:
        cells = [cell_text(c) for c in raw]
        populated = [c for c in cells if c.strip()]
        if not populated:
            continue

        col0 = cells[0].strip() if cells else ""
        qty = cells[1].strip() if len(cells) > 1 else ""
        value = cells[2].strip() if len(cells) > 2 else ""

        # A band row: text in col0, both Qty and Value cells blank.
        if col0 and not qty and not value:
            low = col0.lower()
            if "powered by" in low or "swilerp" in low or col0.startswith("*"):
                continue
            band = _split_band(col0)
            if band:
                current_party, current_loc = band
            continue

        # TOTAL / GRAND TOTAL subtotal rows (col0 exactly a subtotal label).
        if col0.rstrip(":").strip().lower() in _SUBTOTAL_LABELS:
            continue

        product = col0
        if not product or not re.search(r"[A-Za-z0-9]", product):
            continue
        # A real sale line always carries a value.
        if not qty and not value:
            continue

        records.append({
            "party_name": current_party,
            "party_location": current_loc,
            "product_name": product,
            "qty": qty,
            "amount": value,
        })

    detected = {
        "Product Name": "product_name",
        "Qty.": "qty",
        "Value": "amount",
        "Customer": "party_name",
    }
    return records, detected
