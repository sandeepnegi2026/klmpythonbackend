"""KLM (C-Square PharmAssist) "Stock and Sales Mfac Group Wise Report" export
(ANNAPURNA PHARMA AGENCY, "klm st excel.xls" / "KLM_JUNE.xls").

A three-row title/address/period banner sits above a SPARSE positional header row whose
labels are interleaved with blank spacer columns:

    Item |   |   |   | Pack |   | May | Apr | Op. | Pur |   | SP | Sale | SS | Br |   |
    Cr | Db | Adj |   | Bal. |   |   | BVal |   | SVal |   | Order

The body is banded by a single "Manufacturer Group:" row (col0 blank), and every data row
carries the product in col0 with numbers scattered across the fixed positions above; blank
means zero. Because of the blank spacer columns AND the prior-month (May/Apr) and value
(BVal/SVal) columns that have no home, the generic `tabular` reader mis-binds the closing
column (it reads Bal. off a blank/wrong index) and ~60% of rows report closing 0 and fail
sanity. A positional parser that maps each column by its EXACT header token reconciles every
row.

Decoded by 100% row reconciliation across both sample books:

    Bal. = Op. + Pur + SP - Sale - SS + Cr - Db + Adj

so, in canonical fields (closing = opening + purchase + purchase_free - purchase_return
- sales_qty - sales_free + sales_return):

    Op.   -> opening_stock
    Pur   -> purchase_stock
    SP    -> purchase_free    (free/scheme goods received, inflow)
    Sale  -> sales_qty
    SS    -> sales_free       (free/scheme goods issued, outflow)
    Cr    -> sales_return     (credit-note qty back in, inflow)
    Db    -> purchase_return  (debit-note qty out, outflow)
    Adj   -> signed: +ve folds into sales_return (in), -ve into purchase_return (out)
    Br    -> signed like Adj (branch transfer; all-zero in samples, mapped conservatively)
    Bal.  -> closing_stock
    BVal  -> closing_stock_value   (balance value)
    SVal  -> sales_value

May / Apr are prior-month sale qtys (informational) and Order is a pending-order suggestion;
none are stock movement, so they are deliberately left unmapped. SP / SS / Br / Db were all
zero in the samples but are mapped because the header carries them; only Cr and Adj carried
real non-zero movement, and both reconcile exactly.
"""
from extractors.stock_xlsx.parse_common import cell_text

_NUMERIC = (
    "opening_stock", "purchase_stock", "purchase_free", "purchase_return",
    "sales_qty", "sales_free", "sales_return",
)

# Exact compact header token (lowercased, spaces/dots stripped) -> canonical role.
# Blank spacer cells and the informational May/Apr/Order columns produce no token here.
_HEADER_ROLES = {
    "item": "product_name",
    "pack": "pack",
    "op": "opening_stock",
    "pur": "purchase_stock",
    "sp": "purchase_free",
    "sale": "sales_qty",
    "ss": "sales_free",
    "cr": "sales_return",     # credit note -> inflow
    "db": "purchase_return",  # debit note  -> outflow
    "adj": "adj",             # signed
    "br": "br",               # signed (branch transfer)
    "bal": "closing_stock",
    "bval": "closing_stock_value",
    "sval": "sales_value",
}


def _tok(cell):
    return cell_text(cell).strip().lower().replace(" ", "").replace(".", "").replace("'", "")


def _num(cell):
    """blank / '-' / '.' -> 0.0, else float (None if non-numeric junk)."""
    s = cell_text(cell).strip().replace(",", "")
    if s in ("", "-", "--", "---", "."):
        return 0.0
    try:
        return float(s)
    except ValueError:
        return None


def _find_header(rows):
    """Row whose tokens include Item + Bal + BVal + SVal (the distinctive quad)."""
    for idx, row in enumerate(rows[:25]):
        toks = {_tok(c) for c in row if cell_text(c).strip()}
        if {"item", "bal", "bval", "sval"} <= toks:
            return idx
    return None


def _fmt(val):
    return str(int(val)) if val == int(val) else str(val)


def parse_klm_mfac_group_wise_stock(rows):
    header_idx = _find_header(rows)
    if header_idx is None:
        return [], {}
    roles = {}
    for i, cell in enumerate(rows[header_idx]):
        tok = _tok(cell)
        if tok in _HEADER_ROLES and i not in roles:
            roles[i] = _HEADER_ROLES[tok]
    prod_idx = next((i for i, r in roles.items() if r == "product_name"), 0)
    pack_idx = next((i for i, r in roles.items() if r == "pack"), None)
    cls_idx = next((i for i, r in roles.items() if r == "closing_stock"), None)
    if cls_idx is None:
        return [], {}

    records = []
    for raw in rows[header_idx + 1:]:
        cells = [cell_text(c) for c in raw]
        if prod_idx >= len(cells):
            continue
        product = cells[prod_idx].strip()
        if not product:
            # "Manufacturer Group:" band rows carry a blank col0 -> skipped here.
            continue
        low = product.lower()
        if (low.startswith("manufacturer group") or low.startswith("total")
                or low.startswith("grand") or low.startswith("printed using")
                or low.startswith("report date") or low.startswith("page ")):
            continue

        acc = {k: 0.0 for k in _NUMERIC}
        pack = ""
        adj = 0.0
        closing = None
        closing_value = None
        sales_value = None
        skip = False
        for idx, role in roles.items():
            if idx >= len(cells):
                continue
            if role == "product_name":
                continue
            if role == "pack":
                pack = cells[idx].strip()
                continue
            v = _num(cells[idx])
            if role == "closing_stock":
                if v is None:
                    skip = True
                    break
                closing = v
                continue
            if v is None:
                # a stray non-numeric cell in a quantity/value column -> not a real data row
                skip = True
                break
            if role == "closing_stock_value":
                closing_value = v
            elif role == "sales_value":
                sales_value = v
            elif role in ("adj", "br"):
                adj += v
            elif role in acc:
                acc[role] += v
        if skip or closing is None:
            continue

        # Signed Adj/Br: positive is an inflow (credit-like return), negative an outflow.
        if adj >= 0:
            acc["sales_return"] += adj
        else:
            acc["purchase_return"] += -adj

        record = {"product_name": product}
        if pack:
            record["pack"] = pack
        for key, val in acc.items():
            record[key] = _fmt(val)
        record["closing_stock"] = _fmt(closing)
        if closing_value is not None:
            record["closing_stock_value"] = _fmt(closing_value)
        if sales_value is not None:
            record["sales_value"] = _fmt(sales_value)
        records.append(record)

    detected = {
        "Item": "product_name", "Pack": "pack", "Op.": "opening_stock",
        "Pur": "purchase_stock", "SP": "purchase_free", "Sale": "sales_qty",
        "SS": "sales_free", "Cr": "sales_return", "Db": "purchase_return",
        "Adj": "sales_return/purchase_return", "Br": "sales_return/purchase_return",
        "Bal.": "closing_stock", "BVal": "closing_stock_value", "SVal": "sales_value",
    }
    return records, detected
