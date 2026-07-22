from core.header_match import normalize

from extractors.party_xlsx.parse_common import cell_text

# ---------------------------------------------------------------------------
# "Item Wise Summary of Sale By Party" (ASHA AGENCIES). A CUSTOMER-banded export
# numbered with a two-level Sr: an INTEGER Sr row (1, 2, 3 ...) is a CUSTOMER band
# (its name in the Item Name column), and a DECIMAL Sr row (1.1, 1.2, 2.1 ...) is one
# of that customer's ITEM rows, closed by a "Sub Total".
#
# Header: Sr. | Item Name | Qty | Free | Value | cgst | sgst | igst | Amount
#   party  <- Item Name col of an INTEGER-Sr row
#   product<- Item Name col of a DECIMAL-Sr row
#
# Falls to ``tabular`` otherwise -> products but NO party (party_count 0).
# Reconcile: each customer's "Sub Total" Qty/Value == sum of its item rows.
# ---------------------------------------------------------------------------


def _cols(header):
    col = {}
    for i, h in enumerate(header):
        n = normalize(cell_text(h))
        if n and n not in col:
            col[n] = i
    return col


def _c(row, idx):
    return cell_text(row[idx]).strip() if idx is not None and idx < len(row) else ""


def parse_item_wise_summary_sale_by_party(rows):
    header_idx = None
    for i, row in enumerate(rows[:30]):
        n = normalize(" ".join(cell_text(c) for c in row)).replace(" ", "")
        if n.startswith("sr") and "itemname" in n and "qty" in n and "value" in n:
            header_idx = i
            break
    if header_idx is None:
        return [], {}

    col = _cols(rows[header_idx])
    sr_col = col.get("sr.", col.get("sr", 0))
    item_col = col.get("item name", col.get("itemname", 1))
    qty_col = col.get("qty", 2)
    free_col = col.get("free", 3)
    value_col = col.get("value", 4)
    amount_col = col.get("amount", 8)

    records = []
    party = ""
    for row in rows[header_idx + 1:]:
        sr = _c(row, sr_col)
        name = _c(row, item_col)
        if not name:
            continue
        if name.lower().startswith(("sub total", "grand total", "total")):
            continue

        if sr.isdigit():
            # integer Sr -> customer band
            party = name
            continue
        if "." in sr and sr.replace(".", "").isdigit():
            # decimal Sr -> item row for the current customer
            if not party:
                continue
            records.append({
                "party_name": party,
                "party_location": "",
                "product_name": name,
                "qty": _c(row, qty_col),
                "free_qty": _c(row, free_col),
                "amount": _c(row, value_col),
                "net_amount": _c(row, amount_col),
            })

    detected = {
        "Item Name": "product_name",
        "Qty": "qty",
        "Free": "free_qty",
        "Value": "amount",
    }
    return records, detected
