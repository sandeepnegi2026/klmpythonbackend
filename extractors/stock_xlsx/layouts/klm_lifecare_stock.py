"""KLM "Stock And Sales Report(Month)" wide single-header grid (LIFE CARE / YOGIRAM).

Header row (row ~4), one row per product:

  ProductName | OpeningStock | PurchaseQuantity | IILastSalesQty | ILastSalesQty |
  SaleQuantity | TotalStock | Order Qty | StockValueatCostPrice | SaleValue |
  ILastSalesValue | IILastSalesValue | Order Value | ... | UnitDesc |
  SaleReturnQuantity | ... | PurchaseValue | MRP | ... |
  Division Code | Division Name | Division Abbreviation | ... | Order Free Qty

Why a dedicated header-mapped parser (like klm_dstk_stock) instead of the generic
tabular matcher: this KLM/Marg export carries ~35 columns, many of them prior-month
history and rupee-value analytics whose header text fuzzy-collides with the canonical
qty synonyms and STEALS the closing equation's fields:

  * IILastSalesQty / ILastSalesQty are PRIOR-month sales history, not the current
    period's ``SaleQuantity`` — the generic matcher can bind one of them to sales_qty.
  * SaleValue / ItemCost / *Value analytics are rupees, and can land in a qty field.
  * ``Order Qty`` / ``Order Free Qty`` are pending-order columns, not stock movement.
  * SaleReturnQuantity here is a signed net adjustment already reflected in closing
    (rows carry -1 / -2), so subtracting it as sales_return breaks the equation.

Reconciles: TotalStock (closing) = OpeningStock + PurchaseQuantity - SaleQuantity.
(Verified per-row ~97% at 1% tol; e.g. AMOCLAFIX 9+10-9=10, BLEMGUARD 27+10-28=9,
CETALORE 51+0-5=46, and the printed total row 3464+4165-4294~=3332.)

We therefore map ONLY the columns whose meaning is verified, by exact header text,
and deliberately OMIT every history / value / order column so none can steal a field.
"""
from extractors.stock_xlsx.parse_common import cell_text, is_subtotal

# Exact (lowercased, stripped) header text -> canonical field. Everything not listed
# (IILastSalesQty, ILastSalesQty, SaleValue, ItemCost, Order Qty/Value/Free, and all the
# *Value analytics + SaleReturnQuantity) is intentionally absent so it cannot steal a field.
_COL_MAP = {
    "productname": "product_name",
    "openingstock": "opening_stock",
    "purchasequantity": "purchase_stock",
    "salequantity": "sales_qty",
    "totalstock": "closing_stock",
    "stockvalueatcostprice": "closing_stock_value",
    "unitdesc": "pack",
    "mrp": "mrp",
    "division name": "division",
}


def _norm(cell):
    return cell_text(cell).lower().strip()


def parse_klm_lifecare_stock(rows):
    header_idx = None
    for idx in range(min(len(rows), 60)):
        cells = [_norm(c) for c in rows[idx]]
        # Anchor on the two columns unique to this export's header that also drive the
        # closing equation: the product column and the TotalStock (closing) column.
        if "productname" in cells and "totalstock" in cells:
            header_idx = idx
            break
    if header_idx is None:
        return [], {}

    col_to_canonical = {}
    detected = {}
    for i, cell in enumerate(rows[header_idx]):
        key = _COL_MAP.get(_norm(cell))
        if key and key not in col_to_canonical.values():
            col_to_canonical[i] = key
            detected[cell_text(cell)] = key
    # If a mis-detected file lacks either the product column or the closing column,
    # return nothing so it falls through to the generic reader.
    if "product_name" not in col_to_canonical.values() or "closing_stock" not in col_to_canonical.values():
        return [], {}

    records = []
    for raw_row in rows[header_idx + 1:]:
        if not any(cell_text(c) for c in raw_row):
            continue
        if sum(1 for c in raw_row if cell_text(c)) <= 1:
            continue
        record = {}
        for col_idx, key in col_to_canonical.items():
            if col_idx < len(raw_row):
                record[key] = raw_row[col_idx]
        product = cell_text(record.get("product_name", "")).lstrip("*").strip()
        if not product or is_subtotal(product):
            continue
        record["product_name"] = product
        pl = product.lower()
        if any(pl.startswith(k) for k in (
            "opening value", "purchase value", "close value", "sale value",
            "value in rs", "quantity", "---", "page total", "grand total",
            "company", "division", "manufacturer",
        )):
            continue
        # Skip a bare numeric cell mistaken for a product (e.g. a stray totals figure).
        if pl.replace(".", "", 1).replace(",", "").replace("-", "").isdigit():
            continue
        records.append(record)

    return records, detected
