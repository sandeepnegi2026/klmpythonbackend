"""KLM own-vendor "Stock sales statement(Combined)" grid (VISION HEALTHCARE HOLDINGS).

Title row:  Stock sales statement(Combined) for the period DD/MM/YYYY - DD/MM/YYYY
Header row: Product Name | Pack | Rate | Prev.Sale | Opening | Purchase | Total Sale |
            Sale Value | Adj. | Total Closing | Closing Value

Why a dedicated exact-header positional parser (same defensive pattern as
klm_dstk_stock) instead of the generic `tabular` matcher:

  * "Prev.Sale" (previous-period sale, informational) fuzzy-collides with the sales
    synonyms and would steal sales_qty from the real "Total Sale" column.
  * "Adj." (a signed adjustment, informational) has no canonical home and must not
    land in a qty field.
  * "Total Closing" / "Total Sale" are the real movement columns; the generic mapper
    does not reliably prefer them over Prev.Sale, so the movement identity breaks and
    every row fails sanity.

We therefore map ONLY the known columns, by exact (lowercased/stripped) header text,
and DELIBERATELY omit Prev.Sale and Adj.

Rows are grouped by division band rows ("KLM - C1", "KLM - C2", "KLM COSMOQ", ...),
each group closed by a "Total Value ..." row followed by a "Bill Nos. ..." row; a final
"Total ..." grand-total row ends the sheet. All band / total / bill-nos / footer rows
are skipped, as are rows whose product cell is numeric or empty.

Movement identity (verified on every non-zero sampled row):
    closing(Total Closing) = opening(Opening) + purchase(Purchase) - sales(Total Sale)
Blank qty cells mean zero.
"""
from extractors.stock_xlsx.parse_common import cell_text, is_subtotal

# Exact (lowercased, stripped) header text -> canonical field. Prev.Sale and Adj. are
# intentionally absent so they cannot steal a canonical qty field.
_COL_MAP = {
    "product name": "product_name",
    "pack": "pack",
    "rate": "rate",
    "opening": "opening_stock",
    "purchase": "purchase_stock",
    "total sale": "sales_qty",
    "sale value": "sales_value",
    "total closing": "closing_stock",
    "closing value": "closing_stock_value",
}

# Product-cell prefixes that mark a band / footer / total row rather than a real item.
_SKIP_PREFIXES = (
    "total value",
    "total ",
    "bill nos",
    "grand total",
    "opening value",
    "closing value",
    "sale value",
    "quantity",
    "value in rs",
    "page total",
)


def _is_band_or_footer(product):
    pl = product.lower().strip()
    if not pl:
        return True
    if pl in ("total", "klm"):
        return True
    if any(pl.startswith(p) for p in _SKIP_PREFIXES):
        return True
    # Division band rows: "KLM - C1", "KLM - C2", "KLM COSMOQ", "KLM PEDIA DIVISION",
    # "KLM PHARMA DIV", "KLM LABORATRIES LTD", etc.  A band row carries ONLY a division
    # label in the product cell and nothing (or a single stray) elsewhere; we recognise
    # the "KLM ..." forms explicitly and let the "few populated cells" guard in the caller
    # catch the rest.
    if pl.startswith("klm -") or pl.startswith("klm-"):
        return True
    return False


def parse_klm_stock_sales_combined_xlsx(rows):
    header_idx = None
    for idx in range(min(len(rows), 60)):
        cells = [cell_text(c).lower().strip() for c in rows[idx]]
        if (
            "product name" in cells
            and "total closing" in cells
            and "total sale" in cells
            and ("prev.sale" in cells or "prev. sale" in cells)
        ):
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
    if (
        "product_name" not in col_to_canonical.values()
        or "closing_stock" not in col_to_canonical.values()
    ):
        return [], {}

    prod_col = next(i for i, k in col_to_canonical.items() if k == "product_name")

    records = []
    for raw_row in rows[header_idx + 1:]:
        if not any(cell_text(c) for c in raw_row):
            continue
        product = cell_text(raw_row[prod_col]) if prod_col < len(raw_row) else ""
        if not product:
            continue
        if is_subtotal(product) or _is_band_or_footer(product):
            continue
        # A band row like "KLM - C1" carries a label in the product cell and (almost)
        # nothing else; a real product row carries at least Pack/Rate too. Drop rows with
        # only the product cell populated AND no digits anywhere (pure label).
        populated = sum(1 for c in raw_row if cell_text(c))
        has_digit = any(any(ch.isdigit() for ch in cell_text(c)) for c in raw_row)
        if populated <= 1 and not has_digit:
            continue
        # Numeric-only product cell (stray value spill) -> not a product.
        if product.replace(".", "", 1).replace(",", "").replace("-", "", 1).isdigit():
            continue

        record = {}
        for col_idx, key in col_to_canonical.items():
            if col_idx < len(raw_row):
                record[key] = raw_row[col_idx]
        records.append(record)

    return records, detected
