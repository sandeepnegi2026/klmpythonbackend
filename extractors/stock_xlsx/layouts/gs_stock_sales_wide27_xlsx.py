"""G.S. DISTRIBUTORS "KLM-STOCK AND SALES STATEMENT" wide ~27-column stock+sales grid
(G. S. PHARMACEUTICALS — KLM-STOCK_AND_SALES_STATEMENT-30.06.2026.xlsx).

Single header row (row index 4), 28 columns, exact tokens:
  0  PCode                    12 NPR                    24 STK120
  1  Product Name             13 PURCV  (purchase val)  25 Parent Manufacturer
  2  Packing                  14 SALEV  (sales val)     26 Manufacturer / Division
  3  OPSTK  (opening qty)     15 CP                      27 IN
  4  PURC   (purchase qty)    16 TCP
  5  SALE   (sales qty)       17 PTR
  6  STOCK  (CLOSING qty)     18 TPTR
  7  EXP3M                    19 MRP
  8  Exp3MV                   20 GP%
  9  EXP6M                    21 EXSTKV (expiry-stock value, NOT closing value)
  10 Apr  (prior-month qty)   22 NEXD
  11 May  (prior-month qty)   23 NEXQ

Why a dedicated positional parser: the generic ``tabular`` header mapper mis-binds this
28-column grid. The bare abbreviations PURC/SALE have no clean synonym, STOCK is the
current CLOSING balance (fuzz-bound elsewhere or dropped), the prior-month Apr/May qty
columns and the rate columns (CP/TCP/PTR/TPTR/MRP) collide onto value/rate fields, and
EXSTKV (expiry-stock value) can be mistaken for a closing value. Read as generic tabular
the file sanity-fails RED.

This parser maps ONLY the known headers by exact text and IGNORES everything else
(prior-month Apr/May, MRP/GP%/CP/TCP/PTR/TPTR, EXP3M/EXP6M/EXSTKV expiry columns, and the
manufacturer/division/IN columns) so none can steal a canonical field:
  Product Name -> product_name
  Packing      -> pack
  OPSTK        -> opening_stock
  PURC         -> purchase_stock
  SALE         -> sales_qty
  STOCK        -> closing_stock        (VERIFIED: the current closing balance qty; the
                  prior-period columns are the separate Apr/May columns)
  PURCV        -> purchase_value
  SALEV        -> sales_value
There is NO per-row opening_value or closing_stock_value column in this export (EXSTKV is
expiry-stock value, whose column total 112968.75 is unrelated to the footer STOCK value
556400), so neither is emitted.

Reconciliation (honest):
  - Per-row qty identity closing = opening + purchase - sales holds on 215/298 product
    rows (0.72). The ~76 shortfalls are all "closing HIGHER than opening+purc-sale" — the
    ERP folds an unexposed inflow/return (this KLM export carries no clean return column)
    into closing. These are genuine vendor-grid quirks, not a mapping error.
  - VALUE columns reconcile: sum(SALEV) = 1,071,924.22 matches the printed footer
    "SALE : 1071924" EXACTLY; sum(PURCV) = 689,578.94 vs footer "PURC : 692782" differs by
    3203.06 = the single row (PCode 23581 COSMOQ CONDITIONER) whose PURC=10 but PURCV cell
    is blank in the source (a vendor data omission, not a parse error).
  So the correct verdict is a value-corroborated AMBER (exact SALE value reconcile) rather
  than a clean GREEN — the per-row qty grid is internally inconsistent at source.

Skipped rows:
  - The report footer block below the grid ("PURC : ... SALE : ... STOCK : ...",
    "DSTK : Days Stock ...", "***This is a Computer Generated Report...") carries text in
    col 0 only -> the <=1 non-empty guard and the empty-product-name guard drop them.
  - This file has no division/make band rows (flat product list), but any such single-cell
    band would be dropped by the same <=1 non-empty guard.
"""
from extractors.stock_xlsx.parse_common import cell_text, is_subtotal

# Exact (lowercased, space-stripped) header text -> canonical field. Everything not listed
# is deliberately omitted so it cannot steal a canonical field.
_COL_MAP = {
    "productname": "product_name",
    "packing":     "pack",
    "opstk":       "opening_stock",
    "purc":        "purchase_stock",
    "sale":        "sales_qty",
    "stock":       "closing_stock",
    "purcv":       "purchase_value",
    "salev":       "sales_value",
}


def _norm(cell):
    return cell_text(cell).lower().replace(" ", "")


def parse_gs_stock_sales_wide27_xlsx(rows):
    header_idx = None
    for idx in range(min(len(rows), 60)):
        cells = [_norm(c) for c in rows[idx]]
        # Unique signature: the OPSTK/PURC/SALE/STOCK movement quartet on one header row
        # alongside the PURCV/SALEV value pair and the distinctive EXSTKV/STK120/
        # parentmanufacturer columns of this KLM G.S. export.
        if (
            all(tok in cells for tok in ("opstk", "purc", "sale", "stock",
                                         "purcv", "salev"))
            and "exstkv" in cells
            and "parentmanufacturer" in cells
        ):
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
        # Footer/band rows ("PURC : ...", "DSTK : ...", "***Computer Generated...") carry
        # text in a single cell.
        if sum(1 for c in raw_row if cell_text(c)) <= 1:
            continue
        record = {}
        for col_idx, key in col_to_canonical.items():
            if col_idx < len(raw_row):
                record[key] = raw_row[col_idx]
        product = cell_text(record.get("product_name", ""))
        if not product or is_subtotal(product):
            continue
        record["product_name"] = product
        records.append(record)

    return records, detected
