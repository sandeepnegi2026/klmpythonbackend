from core.header_match import normalize

from extractors.party_xlsx.parse_common import cell_text

# ---------------------------------------------------------------------------
# "Product-wise, customer-wise sale/DC details" (FAIRDEAL AGENCIES). A
# PRODUCT-banded party export: each PRODUCT prints a band line (its pack in col 1,
# the division in "Comp", plus a total Qty/Amount and NO voucher), and the CUSTOMERS
# who bought it are the data rows beneath (each with a Vch date + Vch no).
#
# Columns: Particulars | <pack/location> | Comp | Vch date | Vch no | Qty | Scm qty |
#          Scm disc | Amount
#   * PRODUCT band  : Comp filled, Vch date/No blank; col1 = Pack.
#   * CUSTOMER row  : Vch date/No filled; col0 = customer, col1 = location.
#
# It otherwise falls to ``customer_product_banded`` (which assumes the INVERSE
# banding: customer bands, product rows) and comes out with party<->product swapped
# (product "BLEMGUARD FACE SERUM" as party_name, customer "HEALTH CARE MEDICAL STORES"
# as product_name). Here party <- customer row, product <- product band.
#
# Reconcile: each product band's printed total Qty/Amount == sum of its customer rows
# (e.g. BLEMGUARD band Qty 2 / 922.04 == 1/461.02 + 1/461.02).
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


def parse_product_customer_sale_dc_details(rows):
    header_idx = None
    for i, row in enumerate(rows[:30]):
        joined = normalize(" ".join(cell_text(c) for c in row))
        # "details" carries Vch columns, "summary" does not -> require Comp/Amount, not Vch.
        if "particulars" in joined and "amount" in joined and ("comp" in joined or "vch" in joined):
            header_idx = i
            break
    if header_idx is None:
        return [], {}

    col = _cols(rows[header_idx])
    part_col = col.get("particulars", 0)
    comp_col = col.get("comp", 2)
    vchdate_col = col.get("vch date", col.get("vch dt", col.get("vchdate", 3)))
    vchno_col = col.get("vch no", col.get("vchno", 4))
    qty_col = col.get("qty", 5)
    scm_col = col.get("scm qty", col.get("scmqty", 6))
    amount_col = col.get("amount", 8)
    pack_col = 1  # dual use: product Pack on band rows, customer location on data rows

    records = []
    current_product = ""
    for row in rows[header_idx + 1:]:
        part = _c(row, part_col)
        if not part:
            continue
        if part.lower().startswith(("grand total", "total", "report ", "page ", "opening")):
            continue
        comp = _c(row, comp_col)
        vchdate = _c(row, vchdate_col)
        vchno = _c(row, vchno_col)

        # PRODUCT band vs CUSTOMER row: the division (Comp) column is filled ONLY on
        # product header rows; customer rows leave it blank. This is dialect-agnostic --
        # the "details" variant additionally stamps a Vch date/no on customer rows and the
        # "summary" variant does not, so keying on Comp handles both.
        if comp:
            pack = _c(row, pack_col)
            current_product = (part + " " + pack).strip() if pack else part
            continue

        qty = _c(row, qty_col)
        if not current_product or not qty:
            continue

        records.append({
            "party_name": part,
            "party_location": _c(row, pack_col),
            "product_name": current_product,
            "invoice_date": vchdate,
            "invoice_number": vchno,
            "qty": qty,
            "free_qty": _c(row, scm_col),
            "amount": _c(row, amount_col),
        })

    detected = {
        "Particulars": "party_name",
        "Vch no": "invoice_number",
        "Vch date": "invoice_date",
        "Qty": "qty",
        "Amount": "amount",
    }
    return records, detected
