"""KLM "DSTK / OPSTK / PURC / STOCK" positional stock-and-sales export (SATARA-style).

Header row:
  Product Name | Packing | DSTK | OPSTK | PURC | SALE | SALEV | SWQ | SWV | STOCK |
  STOCKV | Apr | Mar | ST120 | EX3M | EX6M | LSQ | IN | OUT

Why a dedicated positional parser (like profit_maker) instead of the generic tabular
header-matcher: the trailing all-zero transfer columns ``IN`` and ``OUT`` exact-match the
canonical synonyms for purchase_stock / sales_qty (score 1.0) and STEAL those fields from
the real ``PURC`` / ``SALE`` columns, while the real closing column ``STOCK`` fuzzy-collides
with opening/total. The generic mapper therefore reads all-zero movement columns and the
file fails sanity. We map ONLY the known column names, by exact header text, by position.

Reconciles: closing(STOCK) = opening(OPSTK) + purchase(PURC) - sales(SALE).
"""
from extractors.stock_xlsx.parse_common import cell_text, is_subtotal

# Exact (lowercased, stripped) header text -> canonical field. Everything not listed
# (DSTK deficit indicator, Apr/Mar period analytics, ST120/EX3M/EX6M aging, LSQ, and the
# all-zero IN/OUT transfer columns) is deliberately omitted so it cannot steal a field.
_COL_MAP = {
    "product name": "product_name",
    "packing": "pack",
    "packi": "pack",                # truncated header in the qty-only PEDIA variant
    "pcod": "hsn_code",
    "opstk": "opening_stock",
    "purc": "purchase_stock",
    "sale": "sales_qty",
    "salev": "sales_value",
    "swq": "sales_return",          # NOTE: SWQ is 0 in every sampled row; mapping is
    "swv": "sales_return_value",    # plausible but UNVERIFIED by reconciliation.
    "stock": "closing_stock",
    "stoc": "closing_stock",         # truncated closing-qty header (KISHORE PHARMACEUTICALS)
    "stockv": "closing_stock_value",
    # NOTE: LZSTK / Mar / Apr / EXP3M / EXP6M are aging/analytics columns, deliberately
    # NOT mapped — LZSTK ("last/aged stock") is a SUBSET of closing, not the closing itself.
}


def parse_klm_dstk_stock(rows):
    header_idx = None
    for idx in range(min(len(rows), 150)):
        cells = [cell_text(c).lower().strip() for c in rows[idx]]
        # The value variant carries STOCKV; the qty-only variant (PEDIA) has only the bare
        # STOCK closing column, so accept either as the header-row signal alongside OPSTK.
        if "opstk" in cells and ("stockv" in cells or "stock" in cells):
            header_idx = idx
            break
    if header_idx is None:
        return [], {}

    col_to_canonical = {}
    detected = {}
    for i, cell in enumerate(rows[header_idx]):
        key = _COL_MAP.get(cell_text(cell).lower().strip())
        if key and key not in col_to_canonical.values():
            col_to_canonical[i] = key
            detected[cell_text(cell)] = key
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
        product = cell_text(record.get("product_name", ""))
        if not product or is_subtotal(product):
            continue
        pl = product.lower().strip()
        if any(pl.startswith(k) for k in (
            "opening value", "purchase value", "close value", "sale value",
            "value in rs", "quantity", "---", "page total", "grand total",
            "company", "division", "manufacturer",
        )):
            continue
        # trailing report furniture: "Medica Ultimate (+91-022-4747-4747)" software
        # credit + "(Report End) (247 Records)" marker — both print in the product
        # column as all-zero phantom rows (the DOSHI "last two rows" defect).
        if pl.startswith("(report end") or "medica ultimate" in pl or "+91-" in pl:
            continue
        if pl.replace(".", "", 1).replace(",", "").isdigit():
            continue
        records.append(record)

    return records, detected
