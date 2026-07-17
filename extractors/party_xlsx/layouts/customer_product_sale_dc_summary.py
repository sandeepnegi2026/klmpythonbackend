"""
"Customer-wise, product-wise sale/DC summary" — MediVision Platinum Excel export
(BLUMAX DISTRIBUTORS / KLM). A two-level banded party report that shares a SINGLE set
of columns for both the customer band and the product lines::

    Particulars | Addr/unit | Comp | Qty | Scm qty | Scm disc | Item disc | Amount
    A UNITED DRUG STORE | SOLAPUR |      | 12 |   |   |   | 1929.46     <- CUSTOMER band
    GA-6 CREAM          | 30GM    | K.L.M|  2 |   |   |   |  278.56     <- product line
    KLM KLIN AHA ...    | 100ML   | KLM L|  2 |   |   |   |  406.1
    ...
                        |         |      |    | Totals: | 0 | 0 | 65842.6   <- grand total

The customer is a *band* row, not a column: its ``Comp`` (division) cell is BLANK and its
``Addr/unit`` holds the customer's town, while its ``Qty``/``Amount`` are that customer's
subtotals. Every product line beneath it carries a non-blank ``Comp`` division code
(K.L.M / KLM L / KLM P). The band's party name carries down onto each product line until
the next band.

The generic ``tabular`` reader maps ``Particulars -> product_name`` (there is no party
column), so the customer band lands in the product column and no ``party_name`` is ever
attached (-> MISSING_REQUIRED_FIELD:party_name). This layout reads the band off the blank
``Comp`` cell, emits only the (Comp-filled) product lines, and stamps each with its
carried-down customer name + town.

Reconciliation (BLUMAX KLM PARTYWISE JUNE): 87 product rows, qty 530, amount 65842.60 ==
printed "Totals: ... 65842.6". The customer-band subtotals (same 530 / 65842.60) are NOT
emitted.
"""
from extractors.party_xlsx.parse_common import cell_text, compact

# Compact title fingerprint (normalize lowercases + strips non-alphanumerics, then compact
# removes spaces): "Customer-wise, product-wise sale/DC summary" -> this token. Distinct from
# the pivot layout's "productwiseareawisesaledcsummary" (that one leads with "area-wise").
_TITLE = "customerwiseproductwisesaledcsummary"
# Exact compact header of the eight-cell column row.
_HEADER = "particularsaddrunitcompqtyscmqtyscmdiscitemdiscamount"


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


def _num(text):
    return text.strip().replace(",", "")


def parse_customer_product_sale_dc_summary(rows):
    header_idx = _header_idx(rows)
    if header_idx is None:
        return [], {}

    records = []
    current_party = ""
    current_location = ""
    for raw in rows[header_idx + 1:]:
        cells = [cell_text(c) for c in raw]
        if len(cells) < 8:
            cells = cells + [""] * (8 - len(cells))
        particulars = cells[0].strip()
        addr_unit = cells[1].strip()
        comp = cells[2].strip()
        qty = cells[3].strip()
        scm_qty = cells[4].strip()
        amount = cells[7].strip()

        # Grand-total footer: "Totals:" sits in the Scm-qty cell with a blank col0.
        if not particulars:
            continue
        # Prepared-by / generator footer line (repeated across every column).
        if "generated at" in particulars.lower() or "medivision" in particulars.lower():
            continue

        # A BLANK Comp (division) cell marks a CUSTOMER band; its Addr/unit is the town and
        # its Qty/Amount are subtotals we do not emit. Advance the carried party + location.
        if not comp:
            current_party = particulars
            current_location = addr_unit
            continue

        # Product line (Comp filled). Stamp the carried customer; skip if none seen yet.
        if not current_party:
            continue
        record = {
            "party_name": current_party,
            "party_location": current_location,
            "product_name": particulars,
            "pack": addr_unit,
            "division": comp,
            "qty": _num(qty),
            "free_qty": _num(scm_qty),
            "amount": _num(amount),
        }
        records.append(record)

    detected = {
        "Particulars": "product_name",
        "Addr/unit": "pack",
        "Comp": "division",
        "Qty": "qty",
        "Scm qty": "free_qty",
        "Amount": "amount",
    }
    return records, detected
