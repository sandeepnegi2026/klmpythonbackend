from core.header_match import map_headers

from extractors.party_xlsx.constants import BARE_TOTAL_RE
from extractors.party_xlsx.parse_common import is_subtotal


def _nonzero(value):
    """True when a cell holds a non-empty, non-zero numeric quantity."""
    text = str(value).strip()
    if not text:
        return False
    try:
        return float(text) != 0
    except (TypeError, ValueError):
        return False


def _is_numeric_cell(val):
    """True if the cell parses as a real number (ignoring commas / trailing symbols).

    SwilERP/Marg sale lines always print a numeric GrsAmt (the value). Footer trailer
    rows put non-numeric TEXT there ("For Satara Pharma", "Authorised Signatory"), so a
    non-numeric amount on an otherwise product-less row flags a trailer, not a sale."""
    s = str(val).strip()
    if not s:
        return False
    s = s.replace(",", "").rstrip("#%").strip()
    if not s:
        return False
    try:
        float(s)
        return True
    except ValueError:
        return False


def records_from_mapped(headers, rows, header_idx):
    header_map = map_headers(headers, "party")
    detected = {raw: info["canonical"] for raw, info in header_map.items()}
    records = []
    last_party = ""
    last_location = ""
    for raw_row in rows[header_idx + 1 :]:
        record = {}
        for idx, header in enumerate(headers):
            key = detected.get(str(header))
            if key:
                record[key] = raw_row[idx] if idx < len(raw_row) else ""
        if not any(str(v).strip() for v in record.values()):
            continue
        party_value = str(record.get("party_name", "")).strip()
        # A "Grand Total" / "Total" footer row carries figures (so the qty guard below would
        # keep it) but its Customer column is a bare total label. Skip it up front so it is not
        # emitted as a party and cannot pollute the carry-down. BARE_TOTAL_RE is anchored to the
        # whole cell, so real names like "TOTAL CARE PHARMA" / "SALES INDIA" are NOT dropped.
        if party_value and BARE_TOTAL_RE.match(party_value):
            continue
        # A grand-TOTAL footer can also print its label in a NON-party column (SALASAR:
        # "TOTAL" sits in the Date cell -- ['TOTAL', '', '', '', qty, free, '', amount]) so
        # the check above cannot see it; the empty party cell then inherits the previous
        # customer via carry-down and the row ships as a phantom sale, doubling the file
        # totals. Gate: the row's OWN party and product cells are both blank (no real sale
        # line lacks both identities) AND some source cell is a bare total label.
        # BARE_TOTAL_RE is anchored to the whole cell, so real names ("TOTAL CARE PHARMA"),
        # plain numbers and dates never match; rows without a total label are untouched.
        if (
            not party_value
            and not str(record.get("product_name", "")).strip()
            and any(BARE_TOTAL_RE.match(str(cell).strip()) for cell in raw_row)
        ):
            continue
        # SwilERP / Marg TRAILER rows (SATARA PHARMA "Medica Ultimate (+91-...)" / "(Report End)
        # (N Records)") print a caption in the Inv No cell and a non-numeric label in the GrsAmt
        # (amount) cell — ['Medica Ultimate (...)', '', ..., 'For Satara Pharma'] — every other
        # cell blank. party/product are blank so carry-down stamps the previous customer, and
        # because invoice_number + amount are both populated (with TEXT), the all-blank guards
        # below and the value-less guard both miss it, so the trailer ships as a phantom sale
        # (2 fake party rows per file). Gate: NO product, NO real qty, and the amount cell is
        # NON-NUMERIC — a real sale line always carries a numeric GrsAmt, so this cannot drop
        # one. Runs before carry-down so the trailer never inherits a party.
        if (
            not str(record.get("product_name", "")).strip()
            and not _is_numeric_cell(record.get("qty", ""))
            and "amount" in record
            and str(record.get("amount", "")).strip()
            and not _is_numeric_cell(record.get("amount", ""))
        ):
            continue
        # An UNLABELED totals footer (KHURANA, SHRI RAM JEE) prints only numbers with no
        # party, product OR serial identity at all — [None,None,None,qty,free,amount,None] —
        # so the label-based guards above never fire and carry-down would stamp it a phantom
        # sale, exactly doubling the file totals. No real sale line lacks all three identities,
        # so drop a row whose own party, product and invoice cells are blank while a mapped
        # numeric column is populated. Runs before carry-down.
        if (
            not party_value
            and not str(record.get("product_name", "")).strip()
            and not str(record.get("invoice_number", "")).strip()
        ):
            numeric_keys = [
                k for k in ("qty", "free_qty", "amount", "net_amount", "taxable_value")
                if k in record
            ]
            if numeric_keys and any(str(record.get(k, "")).strip() for k in numeric_keys):
                continue
        location_value = str(
            record.get("party_location") or record.get("party_area") or ""
        ).strip()
        if party_value:
            last_party = party_value
        elif last_party:
            record["party_name"] = last_party
        if location_value:
            last_location = location_value
        elif last_location and not record.get("party_location"):
            record["party_location"] = last_location
        product = str(record.get("product_name", "")).strip()
        if is_subtotal(product):
            continue
        # A genuine FREE-GOODS / scheme line (SIDDHARTH DRUGS Outward Detail: PRATHAM PHARMA
        # "ONITRAZ SB 1" inv 25910) prints a real party, a real product, a real invoice number
        # and a non-zero Free qty but leaves Qty and NetAmt blank (the paid units sit on a
        # sibling line of the same invoice). It is a real sale row (it moved 4 free units) and
        # dropping it under-counts both the row count and the Free total (699->698 rows, free
        # 36->32). Keep such a row before the value-less-band guard below can discard it.
        is_free_only_line = (
            "free_qty" in record
            and _nonzero(record.get("free_qty"))
            and bool(product)
            and bool(str(record.get("invoice_number", "")).strip())
        )
        # Drop a value-less "band" row: a "Product wise sale list" (VISION HEALTHCARE) prints
        # each customer name as a header ROW in the Product column with no qty and no value —
        # the real party already sits in the Customer column of every product line below it, so
        # this row is noise (blank/carried party, customer-name-as-product). A row whose mapped
        # qty/amount columns are ALL empty is never a sale line. Gated on those columns existing,
        # and placed after the carry-down above so a real party band still propagates. A
        # free-only scheme line (see is_free_only_line) is exempt: it carries a non-zero Free
        # and a real invoice, so it is a sale, not a noise band.
        value_keys = [k for k in ("qty", "amount") if k in record]
        if (
            value_keys
            and all(not str(record.get(k, "")).strip() for k in value_keys)
            and not is_free_only_line
        ):
            continue
        if (
            record.get("product_name")
            or record.get("invoice_number")
            or record.get("qty")
            or is_free_only_line
        ):
            records.append(record)
    return records, detected
