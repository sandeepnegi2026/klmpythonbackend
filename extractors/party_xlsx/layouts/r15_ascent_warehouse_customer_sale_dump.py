"""ASCENT WELLNESS warehouse/customer-wise raw sale dump (party_xlsx).

A raw sales-database export (ASCENT WELLNESS & PHARMA SOLUTIONS) whose header row is
the literal underlying-view column names, in THIS exact order::

    warehouse_city | warehouseid | warehouse_name | customer_id | customer_name |
    ucode | medicinename | transactiontype | salesinvoicedate | cust_pincode |
    cust_area | cust_state | n_mrp | billed_qty | quantity_free | qty | sale_value

This is a SIBLING of ``klm_warehouse_pincode_sale_dump`` (the ARYAN WELLNESS dump) but
a genuinely DIFFERENT column ORDER and column SET:

  * ARYAN has NO ``customer_id`` / ``customer_name`` / ``billed_qty`` columns; its
    customer is ``cust_area`` (col3) and its only quantity is ``qty`` (col14).
  * ASCENT carries the real customer in ``customer_name`` (col4); ``cust_area`` here is
    a route/locality tag ("EKD-HADAPSAR"), NOT the party.

Because the two share the header field NAMES ``warehouse_city`` / ``cust_area`` /
``transactiontype`` / ``salesinvoicedate`` / ``medicinename``, the ASCENT file ALSO
matches the ARYAN positional gate and gets stolen by it -- and read at the wrong
indices (col3 ``customer_id`` -> party, col7 ``transactiontype`` -> product,
col14 ``quantity_free`` -> qty), so every numeric comes out 0 -> RED
COLUMN_MISALIGNMENT. This layout claims the ASCENT export via the ``customer_id`` /
``customer_name`` header run (absent from ARYAN) and reads it HEADER-KEYED (binding
each field by locating its exact header cell, not by a fixed index), so the qty and
value columns are never confused.

Field mapping (by exact header text):

    customer_name    -> party_name
    cust_area        -> party_location (route/locality tag) + cust_state + cust_pincode
    warehouse_city   -> party_location (city, prepended)
    salesinvoicedate -> invoice_date
    medicinename     -> product_name
    ucode            -> hsn_code (raw product code)
    n_mrp            -> mrp
    billed_qty       -> qty          (paid/billed quantity; billed_qty + free == qty col)
    quantity_free    -> free_qty     (scheme/free quantity)
    sale_value       -> amount       (already signed: RET rows carry negative amount)

qty (billed_qty) and value (sale_value) are read from their OWN columns and stay
separate -- qty is NEVER derived from the value column. Returns are pre-signed by the
ERP: RET rows carry negative billed_qty AND negative sale_value, so no sign flip is
done here (verified: all 6458 SALE rows and 789 RET rows are sign-consistent, and
billed_qty + quantity_free == qty holds for every row).

Gate token (spaces-stripped, lowercased column-header run unique to this export):
    ``customer_idcustomer_nameucodemedicinename``
"""
from extractors.party_xlsx.parse_common import cell_text


def _header_idx(rows):
    """Return the index of the ASCENT warehouse/customer DB-field header row, else None.

    Signature: col0 == ``warehouse_city`` PLUS the ``customer_id`` / ``customer_name`` /
    ``medicinename`` / ``billed_qty`` DB fields all present. The ``customer_id`` +
    ``customer_name`` pair is what separates this export from the ARYAN
    ``klm_warehouse_pincode_sale_dump`` dump (which has neither), so the run is unique.
    """
    for idx, row in enumerate(rows[:6]):
        cells = [cell_text(c).strip().lower() for c in row]
        if len(cells) < 15:
            continue
        if (
            cells[0] == "warehouse_city"
            and "customer_id" in cells
            and "customer_name" in cells
            and "medicinename" in cells
            and "billed_qty" in cells
        ):
            return idx
    return None


def detect(rows):
    return _header_idx(rows) is not None


def _colmap(header_cells):
    """Map each known header name to its column index (header-keyed, order-agnostic)."""
    idx = {}
    for i, name in enumerate(header_cells):
        key = name.strip().lower()
        if key and key not in idx:
            idx[key] = i
    return idx


def parse_r15_ascent_warehouse_customer_sale_dump(rows):
    header_idx = _header_idx(rows)
    if header_idx is None:
        return [], {}

    header_cells = [cell_text(c) for c in rows[header_idx]]
    cmap = _colmap(header_cells)

    def gi(name):
        return cmap.get(name)

    i_city = gi("warehouse_city")
    i_party = gi("customer_name")
    i_ucode = gi("ucode")
    i_prod = gi("medicinename")
    i_date = gi("salesinvoicedate")
    i_pin = gi("cust_pincode")
    i_area = gi("cust_area")
    i_state = gi("cust_state")
    i_mrp = gi("n_mrp")
    i_billed = gi("billed_qty")
    i_free = gi("quantity_free")
    i_value = gi("sale_value")

    records = []
    for raw in rows[header_idx + 1:]:
        cells = [cell_text(c) for c in raw]

        def col(i):
            if i is None or i >= len(cells):
                return ""
            return cells[i].strip()

        product = col(i_prod)
        party = col(i_party)
        # Every real sale line carries a medicine name AND a customer name; a row
        # missing either is a footer/blank noise row, not a sale.
        if not product or not party:
            continue

        # party_location: city + locality/route tag + state + pincode (blanks & '0'
        # pincodes skipped so no stray leading/trailing comma appears).
        location = ", ".join(
            part for part in (col(i_city), col(i_area), col(i_state), col(i_pin))
            if part and part != "0"
        )

        record = {
            "invoice_date": col(i_date),
            "product_name": product,
            "hsn_code": col(i_ucode),
            "mrp": col(i_mrp),
            "qty": col(i_billed) or "0",
            "free_qty": col(i_free) or "0",
            "amount": col(i_value) or "0",
            "party_name": party,
            "party_location": location,
        }
        records.append(record)

    detected = {
        "warehouse_city": "party_location",
        "customer_name": "party_name",
        "salesinvoicedate": "invoice_date",
        "medicinename": "product_name",
        "ucode": "hsn_code",
        "n_mrp": "mrp",
        "billed_qty": "qty",
        "quantity_free": "free_qty",
        "sale_value": "amount",
    }
    return records, detected
