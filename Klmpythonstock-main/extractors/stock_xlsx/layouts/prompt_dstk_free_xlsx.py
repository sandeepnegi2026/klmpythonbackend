"""Prompt ERP "Stock Statement (Datewise)" for KLM — the .xls twin of the PDF
``prompt`` stock layout (V.G.RAJA).

Sheet shape (Prompt export, "Powered By: PROMPT +91-281-2230181")::

    Product Name |   |   | Pack |   | OpStk | Pur | Sales | ClStk | A3Mn | Favourite   <- group header
                 |   |   |      |   | Qty   | Qty | Qty   | Qty   | Amount            <- sub-header
    KLM LABORATORIES PVT LTD |  |  |  |  | KLM  COSMO Q                                <- division band
    1 | BLEMGUARD FACE SERUM 30ML |  | 1*30ML |  | 20 | 0 | 0 | 20 | 8298.40 | 0        <- data
    ...
      |   | Total:  |   |   | 215 | 96 | 114 | 197                                     <- footer
      |   | Amount: |   |   | 92521.05 | 36135.22 | 45484.53 |   | 85098.58

Why a dedicated positional parser (like ``klm_dstk_stock``) rather than the generic
``tabular`` matcher:

* The four movement columns carry ONLY the ``Qty`` sub-header — the closing rupee VALUE
  is printed in a separate ``Amount`` column that sits under the group label ``A3Mn``.
  The generic reader keys on the single header row, so it sees ``A3Mn``/``Favourite``
  (an average-3-month analytics + favourite-flag pair) instead of the value column and
  mis-reads the closing amount as a quantity — every row then fails the sanity equation.
* The numeric columns (OpStk/Pur/Sales/ClStk/Amount) and Pack align perfectly by index
  between header and data, but the ``Product Name`` header cell sits at the grid position
  the DATA rows use for the SERIAL index (the product itself is pushed one cell right).
  So product_name is read as the first non-serial text cell between the product-name
  header column and the Pack column, while every numeric field maps by its exact,
  index-aligned header — A3Mn / Favourite / serial / spacer columns never map.

Reconciles exactly: closing(ClStk.Qty) = opening(OpStk) + purchase(Pur) - sales(Sales)
(verified: BLEMGUARD-TX 19 + 0 - 1 = 18 = ClStk.Qty). The ``Amount`` column is the
closing rupee value (closing_stock_value), NOT a quantity.
"""
from extractors.stock_xlsx.parse_common import cell_text, is_subtotal

# Exact (lowercased, stripped) GROUP-header text -> canonical field. A3Mn / Favourite
# (average-3-month movement + favourite flag) are deliberately omitted so they cannot
# steal a quantity field. The closing rupee VALUE is picked up separately from the
# SUB-header "amount" cell (which sits under the A3Mn group label).
_GROUP_MAP = {
    "product name": "product_name",
    "pack": "pack",
    "opstk": "opening_stock",
    "pur": "purchase_stock",
    "sales": "sales_qty",
    "clstk": "closing_stock",
}

_STOP_PRODUCT_PREFIXES = (
    "total", "amount", "bills", "opening value", "purchase value", "close value",
    "sale value", "value in rs", "quantity", "grand total", "page total",
    "company", "division", "manufacturer", "powered by", "for, company",
    "authorized", "authorised",
)


def _is_header_group_row(cells_lower):
    return (
        "opstk" in cells_lower
        and "pur" in cells_lower
        and "sales" in cells_lower
        and "clstk" in cells_lower
    )


def parse_prompt_dstk_free_xlsx(rows):
    header_idx = None
    for idx in range(min(len(rows), 60)):
        cells_lower = [cell_text(c).lower().strip() for c in rows[idx]]
        if _is_header_group_row(cells_lower):
            header_idx = idx
            break
    if header_idx is None:
        return [], {}

    # Map the group-header columns by exact text, first occurrence wins.
    col_to_canonical = {}
    detected = {}
    for i, cell in enumerate(rows[header_idx]):
        key = _GROUP_MAP.get(cell_text(cell).lower().strip())
        if key and key not in col_to_canonical.values():
            col_to_canonical[i] = key
            detected[cell_text(cell)] = key

    # The closing rupee value lives in the SUB-header "amount" column (under A3Mn).
    if header_idx + 1 < len(rows):
        for i, cell in enumerate(rows[header_idx + 1]):
            if cell_text(cell).lower().strip() == "amount" and i not in col_to_canonical:
                col_to_canonical[i] = "closing_stock_value"
                detected[cell_text(cell)] = "closing_stock_value"
                break

    if (
        "product_name" not in col_to_canonical.values()
        or "closing_stock" not in col_to_canonical.values()
        or "opening_stock" not in col_to_canonical.values()
    ):
        return [], {}

    prod_col = next(i for i, k in col_to_canonical.items() if k == "product_name")
    pack_col = next((i for i, k in col_to_canonical.items() if k == "pack"), None)
    # The product name is pushed one cell right of its header (the header cell aligns
    # with the DATA serial). Read it as the first non-serial text cell from the header's
    # product column up to (but not including) the Pack column.
    name_scan_end = pack_col if pack_col is not None and pack_col > prod_col else prod_col + 3

    def _read_product(raw_row):
        for i in range(prod_col, min(name_scan_end, len(raw_row))):
            txt = cell_text(raw_row[i])
            if not txt:
                continue
            # skip a leading serial index (bare integer)
            if txt.replace(".", "", 1).replace(",", "").isdigit():
                continue
            return txt
        return ""

    current_division = ""
    records = []
    for raw_row in rows[header_idx + 1:]:
        if not any(cell_text(c) for c in raw_row):
            continue

        # Division band: e.g. "KLM LABORATORIES PVT LTD | | | | | KLM  COSMO Q".
        # The company sits in col0 and the division label further right; there is no
        # serial and no product in the product column, so it is not a data row.
        band_text = cell_text(raw_row[0]) if raw_row else ""
        if band_text and "laboratories" in band_text.lower():
            # capture the right-most non-empty cell as the division label
            tail = [cell_text(c) for c in raw_row[1:] if cell_text(c)]
            if tail:
                current_division = tail[-1]
            continue

        record = {}
        for col_idx, key in col_to_canonical.items():
            if key == "product_name":
                continue
            if col_idx < len(raw_row):
                record[key] = raw_row[col_idx]
        record["product_name"] = _read_product(raw_row)

        product = cell_text(record.get("product_name", ""))
        if not product:
            continue
        pl = product.lower().strip()
        if is_subtotal(product) or pl.startswith(_STOP_PRODUCT_PREFIXES):
            continue
        # a bare number in the product column is a stray serial/value line, not a product
        if pl.replace(".", "", 1).replace(",", "").isdigit():
            continue

        if current_division:
            record.setdefault("division", current_division)
        records.append(record)

    return records, detected
