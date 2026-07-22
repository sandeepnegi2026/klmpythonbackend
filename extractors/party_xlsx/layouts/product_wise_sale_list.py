from core.header_match import normalize

from extractors.party_xlsx.parse_common import cell_text, split_party_area

# ---------------------------------------------------------------------------
# "Product wise sale list For the period ..." (MODERN PHARMA, J.K.MEDICO, ...). A
# CUSTOMER-banded party export: a customer name prints on its own band line and the
# PRODUCTS it bought are the data rows beneath, ending in a "Customer Total".
#
# Header: Product | Pack | Qty. | Free | Repl. | S.Value | Tot.Value
#   * CUSTOMER band : col0 only (a customer name, no Pack/Qty).
#   * PRODUCT row   : col0=product, col1=pack, col2=qty, col3=free, col5=S.Value,
#                     col6=Tot.Value.
#   * MODERN PHARMA also echoes each product NAME on a bare col0 row immediately
#     before its data row, and prints per-product "Product Wise Total" lines.
#
# Falls to ``tabular`` otherwise, which extracts products but NO party (party_count 0).
# Here party <- customer band, product <- data row.
#
# Reconcile: each customer's "Customer Total" Qty/S.Value == sum of its product rows.
# ---------------------------------------------------------------------------

_SKIP = ("product wise total", "customer total", "grand total", "total", "product wise")


def _cols(header):
    col = {}
    for i, h in enumerate(header):
        n = normalize(cell_text(h))
        if n and n not in col:
            col[n] = i
    return col


def _c(row, idx):
    return cell_text(row[idx]).strip() if idx is not None and idx < len(row) else ""


def _is_num(t):
    t = (t or "").replace(",", "").strip()
    if not t:
        return False
    try:
        float(t)
        return True
    except ValueError:
        return False


def parse_product_wise_sale_list(rows):
    header_idx = None
    for i, row in enumerate(rows[:30]):
        n = normalize(" ".join(cell_text(c) for c in row)).replace(" ", "")
        if "product" in n and "pack" in n and ("svalue" in n or "totvalue" in n):
            header_idx = i
            break
    if header_idx is None:
        return [], {}

    col = _cols(rows[header_idx])
    prod_col = col.get("product", 0)
    pack_col = col.get("pack", 1)
    qty_col = col.get("qty", col.get("qty.", 2))
    free_col = col.get("free", 3)
    sval_col = col.get("svalue", col.get("s.value", 5))
    tval_col = col.get("totvalue", col.get("tot.value", 6))

    body = rows[header_idx + 1:]
    records = []
    party = ""
    for i, row in enumerate(body):
        part = _c(row, prod_col)
        if not part:
            continue
        if part.lower().startswith(_SKIP):
            continue

        qty = _c(row, qty_col)
        if _is_num(qty) and _c(row, pack_col):
            # product data row
            if not party:
                continue
            records.append({
                "party_name": party,
                "party_location": "",
                "product_name": part,
                "pack": _c(row, pack_col),
                "qty": qty,
                "free_qty": _c(row, free_col),
                "amount": _c(row, sval_col),
                "net_amount": _c(row, tval_col),
            })
            continue

        # col0-only text row: a product-NAME echo (MODERN) if the NEXT row is that
        # product's data row; otherwise a new CUSTOMER band.
        nxt = body[i + 1] if i + 1 < len(body) else None
        if nxt is not None and _c(nxt, prod_col) == part and _is_num(_c(nxt, qty_col)):
            continue
        pname, ploc = split_party_area(part)
        party = pname or part

    detected = {
        "Product": "product_name",
        "Pack": "pack",
        "Qty": "qty",
        "Free": "free_qty",
        "S.Value": "amount",
    }
    return records, detected
