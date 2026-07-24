"""
"Detailed Company Wise Area Wise Sales Report" — Marg/KLM bill-wise party export
(CHAITANYA PHARMA / KLM DERMA). Company and party sit in BAND rows, the sale lines are a
bill-wise table beneath each party:

    Detailed Company Wise Area Wise Sales Report ... For Period 01-05-2026 To 31-05-2026
    Bill No | Date | Product | | Packing | BATCH | EXP | | MRP | Qty | Free | Disc | Rate | Amount
    Company :   KLM DERMA                                    <- company/division band (2 cells)
    DR PRAKASH K S,SAGAR,SAGAR                               <- party band (bare single cell)
    S/3,725 | 25-05-2026 | ONITRAZ FORTE | | 10'S | ... | 50 | 25 | | 176.79 | 8839.50  <- sale
    PartyWise SubTotal :                     ... 110 | 55 |    | 28339.5   <- per-party subtotal
    CompanyWise Sub Total :                  ... 882 | 316 |   | 134854.21
    Grand Totals :                           ... 882 | 316 |   | 134854.21

The party is a **bare single-cell band** (`NAME,AREA,CITY`) whose text lands in column 0 — which
is the "Bill No" (invoice) column — so ``customer_product_banded``'s bare-band heuristic (needs the
voucher columns EMPTY) never fires and the file falls to generic ``tabular``, which has no party
column -> RED MISSING_REQUIRED_FIELD:party_name. This reader carries the band's party (and area)
down onto each sale line.

Trailing columns vary: a line with a printed Rate is 14 cells (Rate=col12, Amount=col13); a line
without one is 13 cells (Amount=col12). So Amount is read as the LAST cell and Rate only when a
distinct column precedes it — this is what reconciles to the PartyWise/Grand subtotals.

MAPPING: division <- "Company :" band; party_name / party_location <- bare band (name, area);
product_name/pack/batch_no/expiry/mrp/invoice_number/invoice_date/qty/free_qty/rate <- the fixed
left columns; amount <- last cell.
"""
from core.header_match import normalize

from extractors.party_xlsx.parse_common import cell_text, compact

_TITLE = "areawisesalesreport"


def _header_idx(rows):
    for i, row in enumerate(rows[:15]):
        norm = [normalize(c) for c in row]
        if "bill no" in norm and "product" in norm and "qty" in norm and "amount" in norm:
            return i
    return None


def detect(rows):
    head = compact(" ".join(" ".join(cell_text(c) for c in r) for r in rows[:8]))
    return _TITLE in head and _header_idx(rows) is not None


def _is_dashes(text):
    s = text.strip()
    return bool(s) and set(s) <= set("-")


def _split_party(text):
    """Bare band "NAME,AREA,CITY" -> (name, area). Area and city usually repeat (SAGAR,SAGAR);
    take the first as the location. Collapse doubled spaces in the trade name."""
    parts = [p.strip() for p in text.split(",")]
    name = " ".join(parts[0].split())
    loc = parts[1] if len(parts) > 1 and parts[1] else ""
    return name, loc


def parse_company_area_wise_sales(rows):
    detected = {"Bill No": "invoice_number", "Date": "invoice_date", "Product": "product_name",
                "Packing": "pack", "BATCH": "batch_no", "EXP": "expiry", "MRP": "mrp",
                "Qty": "qty", "Free": "free_qty", "Rate": "rate", "Amount": "amount"}
    hidx = _header_idx(rows)
    if hidx is None:
        return [], detected

    norm = [normalize(c) for c in rows[hidx]]

    def col(name):
        return norm.index(name) if name in norm else None

    ci = {k: col(v) for k, v in {
        "bill": "bill no", "date": "date", "product": "product", "pack": "packing",
        "batch": "batch", "exp": "exp", "mrp": "mrp", "qty": "qty", "free": "free",
        "rate": "rate", "amount": "amount",
    }.items()}

    def at(cells, key):
        i = ci.get(key)
        return cells[i].strip() if (i is not None and i < len(cells)) else ""

    records = []
    division = current_party = current_loc = ""
    for raw in rows[hidx + 1:]:
        cells = [cell_text(c) for c in raw]
        nonempty = [c for c in cells if c.strip()]
        if not nonempty:
            continue
        joined = " ".join(cells)
        low = joined.lower()

        # Company/division band: "Company :  KLM DERMA".
        if cells and cells[0].strip().lower().startswith("company") and ":" in cells[0]:
            rest = [c.strip() for c in cells[1:] if c.strip()]
            division = rest[0] if rest else ""
            if division.upper().startswith("KLM "):  # "KLM DERMA" -> "DERMA" (division convention)
                division = division[4:].strip()
            continue
        # Subtotals / grand totals — skip.
        if "subtotal" in low.replace(" ", "") or "sub total" in low or "grand total" in low:
            continue
        # Separator rows.
        if len(nonempty) == 1 and _is_dashes(nonempty[0]):
            continue

        # Bare single-cell party band (only column 0 populated, has a comma, not a total).
        if len(nonempty) == 1 and cells[0].strip() and "," in cells[0]:
            current_party, current_loc = _split_party(cells[0])
            continue

        # Sale line: needs a product and a numeric qty.
        product = at(cells, "product")
        qty = at(cells, "qty")
        if not product or not qty.replace(",", "").replace(".", "").lstrip("-").isdigit():
            continue
        if not current_party:
            continue
        # Amount is the last populated cell; Rate only when a distinct column precedes it.
        amount = nonempty[-1]
        rate = at(cells, "rate") if (ci.get("rate") is not None and ci["rate"] < len(cells) - 1) else ""
        rec = {
            "division": division,
            "party_name": current_party,
            "party_location": current_loc,
            "product_name": product,
            "pack": at(cells, "pack"),
            "batch_no": at(cells, "batch"),
            "expiry": at(cells, "exp"),
            "mrp": at(cells, "mrp"),
            "invoice_number": at(cells, "bill"),
            "invoice_date": at(cells, "date"),
            "qty": qty.replace(",", ""),
            "free_qty": at(cells, "free").replace(",", "") or "0",
            "rate": rate.replace(",", ""),
            "amount": amount.replace(",", ""),
        }
        records.append(rec)

    return records, detected
