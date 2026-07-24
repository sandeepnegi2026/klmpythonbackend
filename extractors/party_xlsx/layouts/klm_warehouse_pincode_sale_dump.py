"""KLM warehouse/pincode-wise raw sale dump (ARYAN WELLNESS / KLM).

A raw table export straight off the KLM sales database whose header row is the
literal column names of the underlying view::

    warehouse_city | warehouseid | warehouse_name | cust_area | cust_state |
    transactiontype | salesinvoicedate | medicinename | ucode | n_mrp |
    quantity_free | sale_value | cust_pincode | billed_qty | qty

The customer is the ``cust_area`` column (the per-route/per-locality customer the
sale was billed to, e.g. "AMIT MAKHIJA WED.DHANKOT GARHI SEC.102" / "AJMER"); the
``warehouse_name`` is the SELLING vendor (constant "ARYAN WELLNESS PVT LTD ...") and
must NOT be read as the party. A text-keyed ``map_headers`` never binds ``cust_area``
to ``party_name`` (it is not a customer synonym), so the file falls to ``tabular``,
which drops the customer into ``raw_cust_area`` and mis-maps ``salesinvoicedate`` ->
invoice_number, ``ucode`` -> hsn_code, and ``quantity_free`` -> raw_ (lost) -> RED
MISSING_REQUIRED_FIELD:party_name. This layout therefore ignores ``map_headers``
entirely and reads POSITIONALLY off the header row (like ``csquare_raw_invoice_dump``),
binding each column by its INDEX:

    col0  warehouse_city   -> party_location (city)
    col3  cust_area        -> party_name (customer)
    col4  cust_state       -> party_location (state, appended)
    col5  transactiontype  -> SALE / RET (context only; qty & value already signed)
    col6  salesinvoicedate -> invoice_date
    col7  medicinename     -> product_name
    col8  ucode            -> hsn_code (raw product code)
    col9  n_mrp            -> mrp
    col10 quantity_free    -> free_qty
    col11 sale_value       -> amount (already signed: RET rows are negative)
    col12 cust_pincode     -> party_location (pincode, appended)
    col13 billed_qty       -> (== qty; ignored)
    col14 qty              -> qty (already signed: RET rows are negative)

Both the quantity (col14) and the sale value (col11) are carried verbatim from their
own columns and stay separate -- qty is NEVER derived from the value column and vice
versa, so the qty/value split is preserved. Returns are pre-signed by the ERP (RET
rows carry negative qty AND negative sale_value), so no sign flipping is done here.

Gated on the exact raw-column header signature (cells[0]=='warehouse_city' AND
'cust_area', 'transactiontype', 'salesinvoicedate', 'medicinename' all present in the
first row) within the first ~6 rows. This DB-field header run appears in no other
corpus file, so the layout claims only this export and every other file is untouched.
"""
from extractors.party_xlsx.parse_common import cell_text


def _header_idx(rows):
    """Return the index of the raw KLM warehouse/pincode DB-field header row, else None.

    The signature is the exact underlying view's column names: ``warehouse_city`` in
    col0 plus the ``cust_area`` / ``transactiontype`` / ``salesinvoicedate`` /
    ``medicinename`` DB fields. Requiring all five makes the run unique to this dump.
    """
    for idx, row in enumerate(rows[:6]):
        cells = [cell_text(c).strip().lower() for c in row]
        if len(cells) < 12:
            continue
        if (
            cells[0] == "warehouse_city"
            and "cust_area" in cells
            and "transactiontype" in cells
            and "salesinvoicedate" in cells
            and "medicinename" in cells
        ):
            return idx
    return None


def detect(rows):
    return _header_idx(rows) is not None


def parse_klm_warehouse_pincode_sale_dump(rows):
    header_idx = _header_idx(rows)
    if header_idx is None:
        return [], {}

    records = []
    for raw in rows[header_idx + 1:]:
        cells = [cell_text(c) for c in raw]
        if len(cells) < 15:
            continue

        def col(i):
            return cells[i].strip() if i < len(cells) else ""

        product = col(7)
        party = col(3)
        # Every real sale line carries a medicine name AND a customer (cust_area);
        # a row missing either is footer/blank noise, not a sale.
        if not product or not party:
            continue

        # party_location = city + state + pincode (dropped parts skipped so a blank
        # cust_area '0' pincode-only row doesn't produce a stray leading comma).
        location = ", ".join(
            part for part in (col(0), col(4), col(12)) if part and part != "0"
        )

        record = {
            "invoice_date": col(6),
            "product_name": product,
            "hsn_code": col(8),
            "mrp": col(9),
            "qty": col(14) or "0",
            "free_qty": col(10) or "0",
            "amount": col(11) or "0",
            "party_name": party,
            "party_location": location,
        }
        records.append(record)

    detected = {
        "warehouse_city": "party_location",
        "cust_area": "party_name",
        "salesinvoicedate": "invoice_date",
        "medicinename": "product_name",
        "ucode": "hsn_code",
        "n_mrp": "mrp",
        "quantity_free": "free_qty",
        "sale_value": "amount",
        "qty": "qty",
    }
    return records, detected
