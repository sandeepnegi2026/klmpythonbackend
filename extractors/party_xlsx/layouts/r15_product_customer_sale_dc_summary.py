"""
"Product-wise, customer-wise sale/DC summary" — MediVision Platinum Excel export
(RAJ DISTRIBUTORS / KLM). This is the BAND-INVERTED sibling of
``customer_product_sale_dc_summary``: here the PRODUCT is the band row and the
CUSTOMERS are the indented sub-lines. Both share the SAME eight columns::

    Particulars | Addr/unit | Comp | Qty | Scm qty | Scm disc | Item disc | Amount
    EKRAN AQUA GEL          | 50GM        | KLM O |  2 |   |   |   | 515.26   <- PRODUCT band
      EKVIRA MEDICAL STORES | DINDORI ROAD|       |  1 |   |   |   | 257.63   <- customer line
      THE DEOLALI MED STORES| DEOLALI CAMP|       |  1 |   |   |   | 257.63   <- customer line
    MELAPIK EVER NEW        | 20GM        | KLM D |  3 |   |   |   | 407.13   <- next PRODUCT band
      ...
                            |             |       |    | Totals: | 0 | 0 | 4471.47  <- grand total

Banding is the MIRROR of the customer-wise layout: the PRODUCT band carries a
NON-BLANK ``Comp`` (division: KLM O / KLM D / KLM L / KLM P) and no leading
whitespace in ``Particulars``; each customer sub-line has a BLANK ``Comp`` and a
leading two-space indent, and its ``Qty``/``Amount`` are that customer's figures.
The product's name/pack/division carry down onto each customer line until the
next product band.

We emit ONE record per CUSTOMER sub-line (party_name = customer, product_name =
carried product). The product-band subtotal rows are NOT emitted.

Gate: the compact title in the top eight rows is
``productwisecustomerwisesaledcsummary`` (the customer-wise sibling leads with
``customerwiseproductwise...`` and must NOT match here). The eight-cell header is
byte-identical to the sibling, so the TITLE distinguishes them — detect requires
BOTH the header run and this title.

Reconciliation (RAJ DISTRIBUTORS may2026): 8 customer rows, qty 30, amount
4471.47 == the customer-line sum == the product-band sum == printed
"Totals: ... 4471.47". No stock columns exist, so this is a party/sales report.
"""
from extractors.party_xlsx.parse_common import cell_text, compact

# Compact title fingerprint: "Product-wise, customer-wise sale/DC summary".
_TITLE = "productwisecustomerwisesaledcsummary"
# Exact compact header of the eight-cell column row (shared with the sibling layout).
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


def parse_product_customer_sale_dc_summary(rows):
    header_idx = _header_idx(rows)
    if header_idx is None:
        return [], {}

    records = []
    current_product = ""
    current_pack = ""
    current_division = ""
    for raw in rows[header_idx + 1:]:
        cells = [cell_text(c) for c in raw]
        if len(cells) < 8:
            cells = cells + [""] * (8 - len(cells))
        # Detect the leading-indent BEFORE stripping (customer sub-lines are indented).
        raw_col0 = str(cells[0])
        indented = raw_col0[:1].isspace()
        particulars = cells[0].strip()
        addr_unit = cells[1].strip()
        comp = cells[2].strip()
        qty = cells[3].strip()
        amount = cells[7].strip()

        if not particulars:
            continue
        low = particulars.lower()
        if "generated at" in low or "medivision" in low or low.startswith("totals"):
            continue

        # A NON-BLANK Comp with no indent marks a PRODUCT band: advance the carried
        # product/pack/division; its Qty/Amount are product subtotals we do not emit.
        if comp and not indented:
            current_product = particulars
            current_pack = addr_unit
            current_division = comp
            continue

        # Customer sub-line (blank Comp, indented). Stamp the carried product.
        if not current_product:
            continue
        record = {
            "party_name": particulars,
            "party_location": addr_unit,
            "product_name": current_product,
            "pack": current_pack,
            "division": current_division,
            "qty": _num(qty),
            "amount": _num(amount),
        }
        records.append(record)

    detected = {
        "Particulars": "party_name",
        "Addr/unit": "party_location",
        "Comp": "division",
        "Qty": "qty",
        "Amount": "amount",
    }
    return records, detected
