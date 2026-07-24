"""Marg ERP 9+ "Stock & Sales Analysis" movement export (Excel).

Layout signature (sheet tab usually "MARG ERP 9+ Excel Report"; also seen on plain
"Sheet1" exports of the same report):

    row 0-3   vendor name / address / phone / "STOCK & SALES ANALYSIS (DIV) <period>"
    header    a band of OPENING / RECEIPT(=purchase) / ISSUE(=sales) / CLOSING columns
    section   a division banner (one cell repeated across the row, e.g. "KLM PEDIA")
    data      EKRAN AQUA 50GM 1*50GM PC | 15 | 150 | 64 | 101  2/28

Three header shapes are produced by the same ERP and all handled here:

  V1  one header row, movement columns merge the qty + nearest months-to-expiry,
      e.g. "CLOSING M.EXP" with cells like "101  2/28". The generic ``tabular`` path
      casts that to None, so closing reads all-zero and every row fails the sanity
      equation — even though the data is perfect (15 + 150 − 64 == 101).
  V2  two header rows: a group row (OPENING/RECEIPT/ISSUE/CLOSING/DUMP) over a
      QTY./VALUE sub-row, so each movement spans two columns. We keep the QTY column
      (the group-label column) and skip the VALUE column.
  V3  one header row with explicit "Op. Qty." / "Opening Balance Value" pairs.

In every shape we map to the QUANTITY column (never the rupee Value/Balance column)
so the canonical sanity check ``closing = opening + purchase − sales`` reconciles,
and we split the leading number off any cell that glues qty + "M/YY".
"""
import re

from extractors.stock_xlsx.parse_common import cell_text, is_subtotal, to_number

# leading numeric token of a cell, e.g. "101  2/28" -> 101.0, "5 10/26" -> 5.0, "-" -> None
_LEAD_NUM_RE = re.compile(r"^\s*-?[\d,]+(?:\.\d+)?")
# the months-to-expiry tail Marg prints after the closing qty, e.g. "2/28"
_MEXP_RE = re.compile(r"\b(\d{1,2}/\d{2,4})\b")


def _norm(cell):
    return cell_text(cell).upper()


def _lead_number(value):
    text = cell_text(value)
    if not text:
        return None
    m = _LEAD_NUM_RE.match(text)
    return to_number(m.group()) if m else None


def _is_value_col(h):
    """A rupee Value/Balance/Amount/Rate column — never a movement quantity."""
    return any(t in h for t in ("VAL", "BALANCE", "AMOUNT", "AMT", "RATE", "MRP"))


def _movement_of(h):
    """Map a header cell to opening/receipt/issue/closing (the QTY column) or None."""
    if not h or _is_value_col(h):
        return None
    if "OPENING" in h or h.startswith(("OP.", "OP ", "OPN")) or h == "OP":
        return "opening"
    if "RECEIPT" in h or "PURCHASE" in h or "RECPT" in h:
        return "receipt"
    if "ISSUE" in h or "SALE" in h:
        return "issue"
    if "CLOSING" in h or h.startswith(("CL.", "CLS", "CLOS")):
        return "closing"
    return None


def _is_section_row(raw_row):
    """A division banner (e.g. 'KLM PEDIA') that pandas unmerges across every column."""
    non_empty = [cell_text(c) for c in raw_row if cell_text(c)]
    return len(non_empty) >= 2 and len(set(non_empty)) == 1


def _is_qty_value_subheader(cells):
    """Row of QTY./VALUE sub-labels under a group header (the V2 second header row)."""
    toks = [c for c in cells if c]
    if len(toks) < 3:
        return False
    qv = sum(1 for c in toks if "QTY" in c or "VALUE" in c or c == "VAL" or "M.EXP" in c)
    return qv >= max(3, len(toks) // 2)


def _find_header(rows):
    for idx, row in enumerate(rows[:30]):
        cells = [_norm(c) for c in row]
        joined = " ".join(cells)
        has_open = "OPENING" in joined or any(c.startswith("OP.") for c in cells)
        has_recv = "RECEIPT" in joined or "PURCHASE" in joined
        has_issue = "ISSUE" in joined or "SALE" in joined
        has_close = "CLOSING" in joined
        if has_open and has_recv and has_issue and has_close:
            return idx, cells
    return None, None


def parse_marg_erp9_movement(rows):
    header_idx, header_cells = _find_header(rows)
    if header_idx is None:
        return [], {}

    col = {}
    product_col = None
    for i, h in enumerate(header_cells):
        if not h:
            continue
        if product_col is None and ("ITEM" in h or "DESCRIPTION" in h or "PRODUCT" in h):
            product_col = i
        movement = _movement_of(h)
        if movement and movement not in col:
            col[movement] = i
    if product_col is None:
        product_col = 0
    # Need at least the opening/closing pair plus one of receipt/issue for the
    # reconciliation to mean anything; otherwise this isn't the movement layout.
    if "opening" not in col or "closing" not in col or not ({"receipt", "issue"} & col.keys()):
        return [], {}

    # V2: a QTY./VALUE sub-header row directly under the group header — the QTY
    # columns we captured align with the group labels; real data starts one row lower.
    data_start = header_idx + 1
    if data_start < len(rows) and _is_qty_value_subheader([_norm(c) for c in rows[data_start]]):
        data_start += 1

    def at(raw_row, key):
        idx = col.get(key)
        return raw_row[idx] if idx is not None and idx < len(raw_row) else ""

    records = []
    for raw_row in rows[data_start:]:
        if not any(raw_row):
            continue
        if _is_section_row(raw_row):
            continue
        product = cell_text(raw_row[product_col]) if product_col < len(raw_row) else ""
        if not product or is_subtotal(product):
            continue
        pl = product.lower().strip()
        if pl.startswith(("company", "division", "manufacturer", "item name", "product name", "values")):
            continue
        if pl.replace(".", "", 1).replace(",", "").isdigit():
            continue
        if sum(1 for c in raw_row if cell_text(c)) <= 1:
            continue

        closing_raw = cell_text(at(raw_row, "closing"))
        record = {
            "product_name": product,
            "opening_stock": _lead_number(at(raw_row, "opening")) or 0.0,
            "purchase_stock": _lead_number(at(raw_row, "receipt")) or 0.0,
            "sales_qty": _lead_number(at(raw_row, "issue")) or 0.0,
            "closing_stock": _lead_number(closing_raw),
        }
        mexp = _MEXP_RE.search(closing_raw)
        if mexp:
            record["expiry"] = mexp.group(1)
        records.append(record)

    detected = {
        "ITEM DESCRIPTION": "product_name",
        "OPENING": "opening_stock",
        "RECEIPT": "purchase_stock",
        "ISSUE": "sales_qty",
        "CLOSING": "closing_stock",
    }
    return records, detected
