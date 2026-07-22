from core.header_match import normalize

from extractors.party_xlsx.header_detect import detect_header_row
from extractors.party_xlsx.parse_common import cell_text, compact, split_party_area
import re

def _clean_infosoft_party(name, area):
    if area.startswith("-"):
        area = area[1:].strip()
    m = re.search(r'\[\d+\]', name)
    if m:
        name = name[:m.start()]
    name = re.sub(r'^[A-Z0-9]{3,10}-', '', name)
    return name.strip(' -'), area.strip()

def infosoft_band_product(headers):
    header_text = normalize(" ".join(headers))
    return "billno" in compact(header_text) or "bill no" in header_text


_CUST_KW = re.compile(
    r"MEDICAL|PHARMAC|STORES?|AGENC|SURGICAL|MEDICALS|MEDICOS|TRADERS|ENTERPRIS"
    r"|\bDRUG|DISTRIBUT|CHEMIST|HOSPITAL|CLINIC|&\s*GEN|GENERAL",
    re.I,
)


def _bands_look_customer(rows, header_idx):
    """The "->" band rows carry a customer name in the CUSTOMER-banded dialect (band =
    customer, items are the rows) and a product name in the PRODUCT-banded one. ARHAM /
    GANESH ship a richer customer-banded export that ALSO has Bill No/Date/Rate columns, so
    infosoft_band_product() (header-only) wrongly reads it as product-banded and inverts
    party<->product. Deciding orientation from band CONTENT fixes them without touching the
    15 no-BillNo NANDINI files (already customer-banded)."""
    bands = []
    for raw_row in rows[header_idx + 1:]:
        if not raw_row or not cell_text(raw_row[0]).startswith("->"):
            continue
        for cell in raw_row[1:]:
            t = cell_text(cell)
            if t and not t.startswith("->"):
                bands.append(t)
                break
    if not bands:
        return False
    return sum(1 for b in bands if _CUST_KW.search(b)) / len(bands) > 0.5


def parse_infosoft_bandwise(rows):
    header_idx = None
    for idx, row in enumerate(rows[:150]):
        header_text = normalize(" ".join(row))
        if "itemname" in header_text and ("billno" in header_text or "bill" in header_text):
            header_idx = idx
            break
    if header_idx is None:
        header_idx = detect_header_row(rows, min_matches=3)
    if header_idx is None:
        return [], {}
    headers = [str(h) if h else f"col_{i}" for i, h in enumerate(rows[header_idx])]
    col = {normalize(h): i for i, h in enumerate(headers)}
    # Orientation is decided by band CONTENT, not merely by a Bill No column: a
    # customer-banded export can still carry Bill/Date/Rate columns (ARHAM/GANESH).
    product_band = infosoft_band_product(headers) and not _bands_look_customer(
        rows, header_idx
    )
    item_col = col.get("itemname", col.get("item name", 3 if product_band else 1))
    bill_col = col.get("bill no", 1)
    date_col = col.get("date", 2)
    qty_col = col.get("qty", 7 if product_band else 3)
    rate_col = col.get("rate", 9)
    amount_col = col.get("amount", 11 if product_band else 7)
    batch_col = col.get("batch", col.get("expdt", col.get("pack", 4)))

    records = []
    current_product = ""
    current_party = ""
    current_area = ""
    last_item = ""  # customer-banded ditto carry-forward (see below)
    for raw_row in rows[header_idx + 1 :]:
        srno = cell_text(raw_row[0] if raw_row else "")
        if srno.startswith("->"):
            band_text = ""
            for cell in raw_row[1:]:
                text = cell_text(cell)
                if text and not text.startswith("->"):
                    band_text = text
                    break
            if product_band:
                current_product = band_text
            else:
                current_party, current_area = split_party_area(band_text)
                current_party, current_area = _clean_infosoft_party(current_party, current_area)
                last_item = ""  # new customer band -> reset ditto memory
            continue
        if not srno.isdigit():
            continue
        item_text = cell_text(raw_row[item_col] if item_col < len(raw_row) else "")
        qty = cell_text(raw_row[qty_col] if qty_col < len(raw_row) else "")
        if not qty:
            continue
        if product_band:
            if item_text in {"", "-"}:
                continue
            party_name, party_area = split_party_area(item_text)
            party_name, party_area = _clean_infosoft_party(party_name, party_area)
            product_name = current_product
        else:
            # In the CUSTOMER-banded dialect the ItemName cell is the product, and
            # "-" is a DITTO marker meaning "same product as the row above" — a
            # genuine separate invoice line (its own bill no / batch / qty /
            # amount), not a blank. Dropping it silently lost real rows; carry the
            # previous product name forward. A truly empty cell with no prior
            # product is still skipped.
            if item_text == "-":
                if not last_item:
                    continue
                item_text = last_item
            elif not item_text:
                continue
            else:
                last_item = item_text
            party_name, party_area = current_party, current_area
            product_name = item_text
        records.append(
            {
                "party_name": party_name,
                "party_location": party_area,
                "product_name": product_name,
                "invoice_number": cell_text(
                    raw_row[bill_col] if "bill no" in col and bill_col < len(raw_row) else ""
                ),
                "invoice_date": cell_text(
                    raw_row[date_col] if "date" in col and date_col < len(raw_row) else ""
                ),
                "batch_no": cell_text(raw_row[batch_col] if batch_col < len(raw_row) else ""),
                "qty": qty,
                "rate": cell_text(
                    raw_row[rate_col] if "rate" in col and rate_col < len(raw_row) else ""
                ),
                "amount": cell_text(raw_row[amount_col] if amount_col < len(raw_row) else ""),
            }
        )
    detected = {
        "ItemName": "product_name",
        "Bill No": "invoice_number",
        "Date": "invoice_date",
        "Batch": "batch_no",
        "Qty": "qty",
        "Rate": "rate",
        "Amount": "amount",
    }
    return records, detected
