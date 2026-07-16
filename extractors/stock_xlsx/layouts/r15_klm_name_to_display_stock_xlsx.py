"""KLM "Sales And Stock (Detail)" NameToDisplay wide export (JEEVAN DEEP PHARMA —
KLM STOCK.xlsx, misfiled under a Party report folder).

Single header row (row index 8), 22 columns, exact tokens:
  NameToDisplay | Marketing Group | OpStock(Unit1) | OpValue | PurchaseQty(Unit1) |
  In Stock(Unit1) | PurchaseValue | SalesQty(Unit1) | Out Stock(Unit1) | SalesValue |
  Cur.Stock(Unit1) | Cl.Stock As On(Unit1) | Cl.Value | In Stock Value | OpStock(Unit2) |
  SalesReturnQty | SurplusStock(Unit1) | PurchaseReturnQty | ShortageStock(Unit1) |
  IssueLocationTransfer(Unit1) | Out Stock Value | In Transit(Unit1)

Why a dedicated positional/exact-header parser: the generic ``tabular`` header mapper
mangles the columns badly. On APPYBUSH (OpStock 5 / OpValue 510.85 / Cl.Stock 5 /
Cl.Value 510.85) it produced opening_stock=0, closing_stock=0 and shoved 510.85 into
closing_stock_value; on AZACEA (PurchaseQty 5 / PurchaseValue 720) it read
purchase_stock="720" (the VALUE). Every moving row failed sanity -> 0.0 SANITY_FAILED.

This parser maps ONLY the known headers by exact (lowercased, space-stripped) text:
  NameToDisplay          -> product_name
  Marketing Group        -> division
  OpStock(Unit1)         -> opening_stock          (qty)
  OpValue                -> opening_value
  PurchaseQty(Unit1)     -> purchase_stock         (qty; the sole inflow)
  PurchaseValue          -> purchase_value
  SalesQty(Unit1)        -> sales_qty              (qty)
  SalesValue             -> sales_value
  Cl.Stock As On(Unit1)  -> closing_stock          (qty)
  Cl.Value               -> closing_stock_value
  SalesReturnQty         -> sales_return           (adds back to closing)
  PurchaseReturnQty      -> purchase_return        (subtracts from closing)

Deliberately NOT mapped (movement mirror / duplicate / value-only columns that would
double-count or steal a qty field):
  In Stock(Unit1) / Out Stock(Unit1) mirror PurchaseQty / SalesQty (verified equal on
  every product row except one pure location-transfer); Cur.Stock, OpStock(Unit2),
  SurplusStock, ShortageStock, IssueLocationTransfer, In Transit, In Stock Value,
  Out Stock Value -> no canonical field, left out so they cannot steal a qty column.

Reconciles: opening + purchase - sales - purchase_return + sales_return =
Cl.Stock As On on 159/160 moving product rows (0.994). The single off-by row
(KOXITUF TAB: OpStock 17, Out Stock 17, no sale -> a genuine location transfer-out the
vendor recorded only in the movement column) is a real source quirk, not a parse error.
Value corroboration available from the Grand Total footer (OpValue etc.).

Skipped rows:
  - Banner rows (company name / address / "Sales And Stock (Detail)" / date range) carry
    only col 0 -> the <=1 non-empty guard drops them.
  - "Grand Total" footer -> is_subtotal (starts with "grand"/"total").
"""
from extractors.stock_xlsx.parse_common import cell_text, is_subtotal

# Exact (lowercased, space-stripped) header text -> canonical field. Anything not listed
# is deliberately omitted so it cannot steal a canonical field.
_COL_MAP = {
    "nametodisplay":         "product_name",
    "marketinggroup":        "division",
    "opstock(unit1)":        "opening_stock",
    "opvalue":               "opening_value",
    "purchaseqty(unit1)":    "purchase_stock",     # sole inflow qty
    "purchasevalue":         "purchase_value",
    "salesqty(unit1)":       "sales_qty",
    "salesvalue":            "sales_value",
    "cl.stockason(unit1)":   "closing_stock",
    "cl.value":              "closing_stock_value",
    "salesreturnqty":        "sales_return",       # adds back to closing
    "purchasereturnqty":     "purchase_return",    # subtracts from closing
}

# Unique long header run this export alone carries (space-stripped, lowercased).
GATE_TOKEN = "nametodisplaymarketinggroupopstock(unit1)opvaluepurchaseqty(unit1)instock(unit1)"


def _norm(cell):
    return cell_text(cell).lower().replace(" ", "")


def detect(rows):
    flat = "".join(_norm(c) for row in rows[:40] for c in row)
    return GATE_TOKEN in flat


def parse_r15_klm_name_to_display_stock_xlsx(rows):
    header_idx = None
    for idx in range(min(len(rows), 40)):
        cells = [_norm(c) for c in rows[idx]]
        if "nametodisplay" in cells and "cl.stockason(unit1)" in cells and "purchaseqty(unit1)" in cells:
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
    if (
        "product_name" not in col_to_canonical.values()
        or "closing_stock" not in col_to_canonical.values()
    ):
        return [], {}

    records = []
    for raw_row in rows[header_idx + 1:]:
        if not any(cell_text(c) for c in raw_row):
            continue
        # Banner / band rows carry <=1 non-empty cell.
        if sum(1 for c in raw_row if cell_text(c)) <= 1:
            continue
        record = {}
        for col_idx, key in col_to_canonical.items():
            if col_idx < len(raw_row):
                record[key] = raw_row[col_idx]
        product = cell_text(record.get("product_name", ""))
        # "Grand Total" footer.
        if not product or is_subtotal(product):
            continue
        record["product_name"] = product
        records.append(record)

    return records, detected
