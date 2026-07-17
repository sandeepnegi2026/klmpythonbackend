"""
Profit Maker ERP stock-and-sales detailed statement.

Sheet header row contains these specific column names:
  Name | Packing | OStk | PurTot | SRTot | Total1 | SaleTot | PRTot | Total2 | Qoh | QohValue | Age

Column semantics:
  Name       -> product_name
  Packing    -> pack
  OStk       -> opening_stock          (opening balance qty)
  PurTot     -> purchase_stock         (total purchase qty)
  SRTot      -> sales_return           (sales return qty)
  Total1     -> (skip - intermediate: OStk + PurTot - SRTot)
  SaleTot    -> sales_qty              (sales qty)
  PRTot      -> purchase_return        (purchase return qty)
  Total2     -> (skip - intermediate)
  Qoh        -> closing_stock          (Quantity On Hand = closing balance)
  QohValue   -> closing_stock_value    (closing stock value)
  Age        -> (skip - stock age in days, not a canonical field)

Section headers like "Company :KLM DERMA SM" have only 1 non-empty cell → skipped.
"""
from extractors.stock_xlsx.parse_common import cell_text, is_subtotal, to_number

# The CONDENSED variant of this export (SREE TIRUMALA AGENCIES) omits the
# explicit return columns (SRTot, PRTot, Total1, Total2) that the FULL variant
# (ARJUN MEDICAL) carries, and instead prints a single 'TotQty' intermediate
# (verified TotQty == OStk + PurTot on every data row). Without SRTot/PRTot the
# printed columns alone cannot satisfy the stock equation on rows where stock
# left the warehouse without a SaleTot entry (purchase returns / expiry /
# breakage / transfer). In the ERP's own algebra:
#     Qoh = (OStk + PurTot + SR) - (SaleTot + PR)
# so the residual  TotQty - SaleTot - Qoh  is exactly the folded return /
# adjustment outflow that PRTot (or SRTot) would have shown. We derive it back
# from the three printed columns and fold it into purchase_return (residual > 0)
# or sales_return (residual < 0). Caveat: the derived purchase_return figure may
# fold in expiry/breakage/transfer, not only true purchase returns.
_TOTQTY_KEY = "totqty"
_SRTOT_KEY = "srtot"
_PRTOT_KEY = "prtot"

# Expected Profit Maker column-name → canonical key mapping
_COL_MAP = {
    "name":       "product_name",
    "packing":    "pack",
    "ostk":       "opening_stock",
    "purtot":     "purchase_stock",
    "srtot":      "sales_return",
    "saletot":    "sales_qty",
    "prtot":      "purchase_return",
    "qoh":        "closing_stock",
    "qohvalue":   "closing_stock_value",
    # Total1, Total2, Age intentionally omitted
}

_SKIP_COLS = {"total1", "total2", "age"}


def parse_profit_maker(rows):
    """Parse Profit Maker ERP stock-and-sales detailed report."""
    # Find the header row containing 'Name', 'OStk', and 'Qoh'
    header_idx = None
    for idx in range(min(len(rows), 150)):
        cells = [cell_text(c).lower().replace(" ", "") for c in rows[idx]]
        if "name" in cells and "ostk" in cells and "qoh" in cells:
            header_idx = idx
            break

    if header_idx is None:
        return [], {}

    # Build index → canonical key mapping from the header row
    header = [cell_text(c) for c in rows[header_idx]]
    norm_header = [h.lower().replace(" ", "") for h in header]
    col_to_canonical = {}  # col_index → canonical key
    detected = {}          # raw header → canonical key (for display)

    for i, h in enumerate(header):
        key = _COL_MAP.get(h.lower().replace(" ", ""))
        if key:
            col_to_canonical[i] = key
            detected[h] = key

    if "product_name" not in col_to_canonical.values():
        return [], {}

    # CONDENSED-variant gate: header carries 'TotQty' but neither 'SRTot' nor
    # 'PRTot'. The full 12-col variant keeps its explicit return columns → gate
    # false → residual derive skipped → byte-identical output. When gated on,
    # locate the TotQty intermediate column so we can recover the folded returns.
    condensed = (
        _TOTQTY_KEY in norm_header
        and _SRTOT_KEY not in norm_header
        and _PRTOT_KEY not in norm_header
    )
    totqty_idx = norm_header.index(_TOTQTY_KEY) if condensed else None

    records = []
    for raw_row in rows[header_idx + 1:]:
        # Skip empty rows
        if not any(cell_text(c) for c in raw_row):
            continue

        # Skip section/division header rows (only 1 non-empty cell)
        non_empty = sum(1 for c in raw_row if cell_text(c))
        if non_empty <= 1:
            continue

        # Build record
        record = {}
        for col_idx, canonical_key in col_to_canonical.items():
            if col_idx < len(raw_row):
                record[canonical_key] = raw_row[col_idx]

        # Validate product name
        product = cell_text(record.get("product_name", ""))
        if not product or is_subtotal(product):
            continue

        # Skip footer/summary rows that start with known keywords
        pl = product.lower()
        if any(pl.startswith(k) for k in (
            "opening value", "purchase value", "close value",
            "sale value", "---", "page total", "grand total"
        )):
            continue

        # CONDENSED variant only: recover the folded return / adjustment outflow.
        # residual = TotQty - SaleTot - Qoh ; only when all three are clean
        # numbers. residual > 0 → purchase_return ; residual < 0 → sales_return ;
        # residual == 0 → no-op (both left absent, e.g. the COSMOCORE files).
        if condensed and totqty_idx is not None and totqty_idx < len(raw_row):
            totqty = to_number(raw_row[totqty_idx])
            saletot = to_number(record.get("sales_qty"))
            qoh = to_number(record.get("closing_stock"))
            if totqty is not None and saletot is not None and qoh is not None:
                residual = totqty - saletot - qoh
                if residual > 0:
                    record["purchase_return"] = residual
                elif residual < 0:
                    record["sales_return"] = -residual

        records.append(record)

    return records, detected
