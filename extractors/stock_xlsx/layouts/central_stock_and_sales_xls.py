"""CENTRAL DISTRIBUTORS (KLM custom ERP) "Stock And Sales Report" — one BIFF .xls.

Title band (rows 0-4): vendor name / address / "Stock And Sales Report from dd/mm to dd/mm".
Header row (row ~5), 22 exact-text columns:

    ProductCode | ProductName | Pack | ManufactureName | LMS | LMS Total | Op.Stock |
    Opening Total | Purch.Qty | PurchFreeQty | SaleQty | FreeQty | Sl.Ret.Qty |
    BR/E/D/R | Repl | AdjQty | Cl.Stock | Sales Value | Free Value | Cl.Value |
    PurchValue | ExpiryDate

Blank cells and "-" mean zero.

Why a dedicated positional parser (generic `tabular` extracts 0 rows):
  * core.header_match maps "ProductCode" (col 0) -> product_name via a 0.88 contains-hit
    and first-come dedupe then leaves the true "ProductName" (col 1) unmapped, so every
    record's product_name becomes a bare numeric code and tabular's total-row guard
    (pl.replace('.','',1).isdigit()) skips ALL 157 rows.
  * Even with product fixed, PurchFreeQty and AdjQty have no clean synonym, "Repl" fuzzy-
    binds order_qty and "LMS Total" binds total_stock, so the adjusted rows fail sanity.

We bind ONLY the known columns by exact compact header text and deliberately OMIT
ProductCode / LMS / LMS Total / Opening Total / BR-E-D-R / Repl / Free Value /
PurchValue / ExpiryDate so they cannot steal canonical fields.

Reconcile (verified 157/157 rows):

    Cl.Stock = Op.Stock + Purch.Qty + PurchFreeQty - SaleQty - FreeQty + Sl.Ret.Qty + AdjQty

canonical map:

    ProductName    -> product_name
    Pack           -> pack
    Op.Stock       -> opening_stock
    Purch.Qty      -> purchase_stock
    PurchFreeQty   -> purchase_free
    SaleQty        -> sales_qty
    FreeQty        -> sales_free
    Sl.Ret.Qty     -> sales_return       (inflow)
    AdjQty         -> signed: +ve folds into sales_return (in), -ve into purchase_return (out)
    Cl.Stock       -> closing_stock
    Sales Value    -> sales_value
    Cl.Value       -> closing_stock_value

The final all-blank footer row (only the *Total / *Value cells populated) is skipped.
Printed grand totals: Sales Value 80,390.309 / Cl.Value 709,006.92 / PurchValue
106,807.18 / Opening Total 706,804.95 / LMS Total 213,252.953.
"""
from extractors.stock_xlsx.parse_common import cell_text

_NUMERIC = (
    "opening_stock", "purchase_stock", "purchase_free", "purchase_return",
    "sales_qty", "sales_free", "sales_return",
)

# canonical role keyed by the EXACT compact (lower, no-space, no-dot) header token.
_ROLE_BY_TOKEN = {
    "productname": "product_name",
    "pack": "pack",
    "opstock": "opening_stock",
    "purchqty": "purchase_stock",
    "purchfreeqty": "purchase_free",
    "saleqty": "sales_qty",
    "freeqty": "sales_free",
    "slretqty": "sales_return",
    "adjqty": "adj",
    "clstock": "closing_stock",
    "salesvalue": "sales_value",
    "clvalue": "closing_stock_value",
}

_VALUE_ROLES = {"sales_value", "closing_stock_value"}

_SKIP_PREFIXES = (
    "total", "grand", "product", "opening", "closing", "generated",
    "stock and sale", "from", "manufacture",
)


def _compact(cell):
    return cell_text(cell).strip().lower().replace(" ", "").replace(".", "").replace("/", "")


def _num(cell):
    """Numeric cell reader: blank / '-' -> 0.0, otherwise the float (None if junk)."""
    s = cell_text(cell).strip()
    if s in ("", "-", "--", "---", ".", "*"):
        return 0.0
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def _find_header(rows):
    """Header is the row whose first three compact cells are productcode|productname|pack."""
    for idx, row in enumerate(rows[:25]):
        compact = [_compact(c) for c in row]
        if compact[:3] == ["productcode", "productname", "pack"]:
            return idx
    return None


def _fmt(v):
    return str(int(v)) if v == int(v) else str(v)


def parse_central_stock_and_sales_xls(rows):
    header_idx = _find_header(rows)
    if header_idx is None:
        return [], {}

    roles = {}
    for idx, cell in enumerate(rows[header_idx]):
        role = _ROLE_BY_TOKEN.get(_compact(cell))
        if role is not None:
            roles[idx] = role

    prod_idx = next((i for i, r in roles.items() if r == "product_name"), 1)
    cls_idx = next((i for i, r in roles.items() if r == "closing_stock"), None)

    records = []
    for raw in rows[header_idx + 1:]:
        cells = [cell_text(c) for c in raw]
        if prod_idx >= len(cells):
            continue
        product = cells[prod_idx].strip()
        low = product.lower()
        if not product or low.startswith(_SKIP_PREFIXES):
            continue
        # footer / section band: one merged text repeated across every populated cell
        non_empty = [c for c in cells if c.strip()]
        if len(non_empty) > 1 and len(set(non_empty)) == 1:
            continue

        acc = {k: 0.0 for k in _NUMERIC}
        pack = ""
        adj = 0.0
        closing = None
        sales_value = None
        closing_value = None
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
            if v is None:
                skip = True
                break
            if role == "closing_stock":
                closing = v
            elif role == "sales_value":
                sales_value = v
            elif role == "closing_stock_value":
                closing_value = v
            elif role == "adj":
                adj += v
            elif role in acc:
                acc[role] += v
        if skip or closing is None:
            continue

        # Signed AdjQty: positive is an inflow (added like a return), negative an outflow.
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
        if sales_value is not None:
            record["sales_value"] = _fmt(sales_value)
        if closing_value is not None:
            record["closing_stock_value"] = _fmt(closing_value)
        records.append(record)

    detected = {
        "ProductName": "product_name", "Pack": "pack", "Op.Stock": "opening_stock",
        "Purch.Qty": "purchase_stock", "PurchFreeQty": "purchase_free",
        "SaleQty": "sales_qty", "FreeQty": "sales_free", "Sl.Ret.Qty": "sales_return",
        "AdjQty": "sales_return/purchase_return", "Cl.Stock": "closing_stock",
        "Sales Value": "sales_value", "Cl.Value": "closing_stock_value",
    }
    return records, detected
