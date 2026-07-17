"""C-Square raw DB-field invoice dump (HERITAGE MARKTEERS / KLM per-division books).

A raw table export straight off the C-Square database whose header row is the
literal column names of the underlying view::

    n_srno | d_inv_date | c_item_code | c_name | c_name | n_qty | n_scheme_qty |
    n_sale_rate | c_cust_code | c_name | c_code | c_name | c_add_3 | c_city

The header repeats ``c_name`` FOUR times (item name, pack, customer name, and the
division/firm name), so a text-keyed ``map_headers`` clobbers those columns onto a
single canonical key and the customer (col 9) is dropped -> RED
MISSING_REQUIRED_FIELD:party_name. This layout therefore ignores ``map_headers``
entirely and reads POSITIONALLY off the header row (like stock_pdf's
``pharmassist_mfac``), binding each column by its INDEX:

    col0  n_srno        -> invoice_number
    col1  d_inv_date    -> invoice_date
    col2  c_item_code   -> hsn_code (raw product code)
    col3  c_name (#1)   -> product_name (item name)
    col4  c_name (#2)   -> pack
    col5  n_qty         -> qty
    col6  n_scheme_qty  -> free_qty
    col7  n_sale_rate   -> rate
    col9  c_name (#3)   -> party_name (customer name)
    col12 c_add_3       -> party address (folded into party_location)
    col13 c_city        -> party_location

``amount = qty * rate`` (verified: KENZ LOTION qty 3 x rate 178.57 = 535.71, the
printed taxable value). The qty (col5) and value/rate (col7) columns stay separate —
amount is derived from rate, never the reverse, so the qty/value split is preserved.

Gated on the exact raw-column header signature (cells[0]=='n_srno' AND
cells[1]=='d_inv_date' AND 'c_cust_code' present AND >=3 'c_name' cells) within the
first ~10 rows. This DB-field header run appears in no other corpus file, so the
layout claims only this export and every other file is untouched.
"""
from extractors.party_xlsx.parse_common import cell_text


def _header_idx(rows):
    """Return the index of the raw C-Square DB-field header row, else None.

    The signature is the exact underlying view's column names: ``n_srno`` in col0,
    ``d_inv_date`` in col1, a ``c_cust_code`` column, and the four repeated ``c_name``
    columns (item/pack/customer/firm). Requiring >=3 ``c_name`` cells plus the two
    anchor tokens makes the run unique to this dump.
    """
    for idx, row in enumerate(rows[:10]):
        cells = [cell_text(c).strip().lower() for c in row]
        if len(cells) < 10:
            continue
        if (
            cells[0] == "n_srno"
            and cells[1] == "d_inv_date"
            and "c_cust_code" in cells
            and cells.count("c_name") >= 3
        ):
            return idx
    return None


def detect(rows):
    return _header_idx(rows) is not None


def parse_csquare_raw_invoice_dump(rows):
    header_idx = _header_idx(rows)
    if header_idx is None:
        return [], {}

    records = []
    for raw in rows[header_idx + 1:]:
        cells = [cell_text(c) for c in raw]
        if len(cells) < 8:
            continue

        def col(i):
            return cells[i].strip() if i < len(cells) else ""

        product = col(3)
        party = col(9)
        # Every real sale line carries an item name AND a customer; a row missing
        # either is footer/blank noise, not a sale.
        if not product or not party:
            continue

        qty = col(5)
        rate = col(7)
        try:
            amount = f"{float(qty.replace(',', '')) * float(rate.replace(',', '')):.2f}"
        except ValueError:
            amount = ""

        address = col(12)
        city = col(13)
        location = ", ".join(part for part in (address, city) if part)

        record = {
            "invoice_number": col(0),
            "invoice_date": col(1),
            "hsn_code": col(2),
            "product_name": product,
            "pack": col(4),
            "qty": qty or "0",
            "free_qty": col(6) or "0",
            "rate": rate,
            "party_name": party,
            "party_location": location,
        }
        if amount:
            record["amount"] = amount
        records.append(record)

    detected = {
        "n_srno": "invoice_number",
        "d_inv_date": "invoice_date",
        "c_item_code": "hsn_code",
        "c_name": "product_name",
        "n_qty": "qty",
        "n_scheme_qty": "free_qty",
        "n_sale_rate": "rate",
    }
    return records, detected
