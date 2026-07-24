"""Marg (ERP 9+) "STOCK & SALES ANALYSIS" — SPELLED-OUT wide 2-row-header GRID (YUVEE ENTERPRISE).

Same movement family as ``marg_stock_analysis_text`` (the abbreviated grid variant) but this
export spells the column groups out ("SALES RETURN", "SAMPLE", "PURCHASE RETURN") and uses arrow
separators ("<-----", "---->") instead of the abbreviated S/R + REPL/ + FREE SAMPLE + T/F tokens
the existing grid gate keys on. It also splits every quantity into its own physical column with a
2-row header, so the generic ``tabular`` flat header-map cannot resolve it and ~72% of rows fail
sanity.

Two header rows (row4 group labels + row5 sub labels) span 22 columns.  Fixed positional map,
verified against the printed per-division TOTAL rows:

    idx  group / sub           canonical
    ---  --------------------  --------------------------------------------------
     0   ITEM DESCRIPTION      product_name (+ pack peeled from the same cell)
     1   OPENING / QTY.        opening_stock
     2   STOCK   / VALUE       opening_value
     3   <----- / QTY.         purchase_stock
     4   PURCHASE / FREE       purchase_free
     5   ----> / VALUE         purchase_value
     6   <-- / QTY.            sales_return           (inflow — adds stock)
     7   SALES RETURN / FREE   (folded into sales_return)
     8   ---> / VALUE          (ignored — return value)
     9   OTHER / QTY.          (ignored — other-in, all 0 in sample)
    10   TOTAL / QTY.          (ignored — derived running total)
    11   <----- / QTY.         sales_qty              (outflow)
    12   SALES / FREE          sales_free             (outflow)
    13   -------> / VALUE       sales_value
    14   SAMPLE / QTY.         (ignored — sample)
    15   STOCK / QTY.          (ignored — T/F qty)
    16   T/F / VALUE           (ignored — T/F value)
    17   PURCHASE / QTY.       purchase_return        (outflow — removes stock)
    18   RETURN / VALUE        (ignored — purchase-return value)
    19   OTHER / QTY.          (ignored — other-out)
    20   CLOSING / QTY.        closing_stock
    21   STOCK / VALUE         closing_stock_value

Reconciliation (verified on every printed division TOTAL):
    closing = opening + purchase_stock + purchase_free + sales_return
              - purchase_return - sales_qty - sales_free
    GYNEC TOTAL: 194 + 2 + 38 + 0 - 20 - 64 - 26 = 124 = printed CLOSING QTY.
    TRIPTOFER : 46 + 2 + 38 + 0 - 0 - 20 - 10 = 56 = printed CLOSING QTY.

Division band rows (e.g. "KLM LABORATIRES(GYNEC DIV)") repeat one value across every cell and are
recorded as the current ``division`` but not emitted; per-division "TOTAL" footers are skipped.
"""
import re

from extractors.stock_xlsx.parse_common import cell_text, is_subtotal, to_number

# Fixed-index positional map: source column index -> canonical stock field.
_COL_MAP = {
    1:  "opening_stock",
    2:  "opening_value",
    3:  "purchase_stock",
    4:  "purchase_free",
    5:  "purchase_value",
    11: "sales_qty",
    12: "sales_free",
    13: "sales_value",
    17: "purchase_return",
    20: "closing_stock",
    21: "closing_stock_value",
}
# Columns 6+7 both fold into sales_return (qty + free, both inflow adjustments).
_SALES_RETURN_COLS = (6, 7)

_WS_SPLIT = re.compile(r"\s{2,}")
# A pack-ish trailing group: starts with a digit or "N*" pattern (e.g. "1*10 TB", "100 ML", "30 GM").
_PACK_RE = re.compile(r"^\d")
# Unit noise that trails the pack in every product cell.
_UNIT_TOKENS = {"PCS", "PC", "NOS", "NO", "BOX", "BTL", "STR", "STRIP"}


def _split_name_pack(cell):
    """Split the fixed-width col-0 cell into (product_name, pack).

    The cell is padded so that name / pack / unit are separated by runs of 2+ spaces, e.g.
    "ESSFOL TAB              1*10 TB  PCS" -> ("ESSFOL TAB", "1*10 TB").  When the pack is only
    single-space-glued to the name (e.g. "BLEMGUARD-TX FACE SERUM 30ML  PCS") the whole descriptor
    stays in the name — safer than guessing a split point.
    """
    text = cell.strip()
    parts = [p.strip() for p in _WS_SPLIT.split(text) if p.strip()]
    if not parts:
        return "", ""
    # Drop a trailing bare unit token ("PCS") so it never leaks into the pack.
    if len(parts) >= 2 and parts[-1].upper() in _UNIT_TOKENS:
        parts = parts[:-1]
    if len(parts) == 1:
        return parts[0], ""
    pack = parts[-1]
    if _PACK_RE.match(pack):
        return " ".join(parts[:-1]), pack
    # Trailing group isn't pack-shaped: keep everything in the name.
    return " ".join(parts), ""


def _find_header(rows):
    """Return the group-header row index whose col0 == 'ITEM DESCRIPTION' with an 'OPENING' band."""
    for i in range(min(len(rows), 40)):
        row = rows[i]
        if not row:
            continue
        first = cell_text(row[0]).strip().upper()
        if first == "ITEM DESCRIPTION":
            band = " ".join(cell_text(c).upper() for c in row)
            if "OPENING" in band and "CLOSING" in band and "SALES RETURN" in band:
                return i
    return None


def _is_division_band(row):
    """Division/section banner: every populated cell carries the SAME text (spanned merge)."""
    non_empty = [cell_text(c) for c in row if cell_text(c)]
    return len(non_empty) >= 2 and len(set(non_empty)) == 1


def _num(row, idx):
    if idx < len(row):
        val = to_number(row[idx])
        return val if val is not None else 0.0
    return 0.0


def parse_marg_stock_analysis_wide_xlsx(rows):
    header_idx = _find_header(rows)
    if header_idx is None:
        return [], {}

    # Data starts after the 2-row header (group row + sub-label row).
    start = header_idx + 2

    records = []
    division = ""
    for row in rows[start:]:
        if not row or not any(cell_text(c) for c in row):
            continue
        if _is_division_band(row):
            division = cell_text(row[0]).strip()
            continue

        product_cell = cell_text(row[0]).strip()
        if not product_cell:
            continue
        if product_cell.upper() == "TOTAL" or is_subtotal(product_cell):
            continue
        pl = product_cell.lower()
        if pl.startswith(("item description", "value in rs", "quantity")):
            continue
        # A genuine data row carries a numeric movement block; a stray label row does not.
        if sum(1 for c in row[1:] if to_number(c) is not None) < 4:
            continue

        name, pack = _split_name_pack(product_cell)
        if not name:
            continue

        record = {"product_name": name}
        if pack:
            record["pack"] = pack
        for idx, key in _COL_MAP.items():
            record[key] = _num(row, idx)
        record["sales_return"] = sum(_num(row, i) for i in _SALES_RETURN_COLS)
        if division:
            record["division"] = division
        records.append(record)

    detected = {
        "ITEM DESCRIPTION": "product_name",
        "OPENING": "opening_stock",
        "PURCHASE": "purchase_stock",
        "PURCHASE FREE": "purchase_free",
        "SALES RETURN": "sales_return",
        "SALES": "sales_qty",
        "SALES FREE": "sales_free",
        "PURCHASE RETURN": "purchase_return",
        "CLOSING": "closing_stock",
    }
    return records, detected
