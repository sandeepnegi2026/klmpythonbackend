"""KLM/Marg "STOCK & SALES ANALYSIS" REDUCED Receipt/Issue/Closing GRID (.xls).

KRISHNA MEDICARE (SANGRUR) exports the KLM "STOCK & SALES ANALYSIS" report as a real
multi-cell GRID (NOT the single-column text dump handled by
`stock_sales_analysis_oic_xlsx` / `marg_stock_open_rcpt_issue_xls`) whose two-row header
is::

    ITEM DESCRIPTION | RECEIPT | ISSUE | CLOSING
                     |  QTY.   | QTY.  | QTY.    | VALUE

i.e. only THREE movement quantity columns — RECEIPT, ISSUE, CLOSING(qty) — plus a single
CLOSING VALUE column. There is NO opening and NO purchase column in the source. Because
the "VALUE" sub-label sits in the SECOND header row (row+1) while the primary header row
carries only the group labels, the generic `tabular` reader binds RECEIPT/ISSUE/CLOSING
correctly but DROPS the closing VALUE column (its header cell in the group row is empty),
so `closing_stock_value` is never populated. That defeats the value-corroboration
downgrade for this structurally `no_inflow` report (no opening/purchase => the quantity
identity opening+purchase-sales=closing can never hold) and it lands RED instead of the
faithful-but-unreconcilable AMBER.

This parser reads the two-row header positionally and maps by EXACT sub-column identity:

    ITEM DESCRIPTION -> product_name
    RECEIPT   (QTY.) -> purchase_stock
    ISSUE     (QTY.) -> sales_qty
    CLOSING   (QTY.) -> closing_stock
    CLOSING   (VALUE)-> closing_stock_value     (the value column captured -> corroborates)

'-' means nil (0). Division band rows ("KLM LAB (COSMOQ)") are single-cell and dropped;
the trailing "TOTAL" subtotal row is skipped. Quantities are NEVER derived from the value
column. The closing VALUE grand total on the TOTAL row (e.g. 25074.91) equals the summed
per-row closing values, so value_total_corroborated fires and the report is surfaced as a
faithful `no_inflow` AMBER rather than a false RED.

Gate token (compact contiguous header run, spaces-stripped, lowercased, unique to this
reduced GRID form): ``itemdescriptionreceiptissueclosing`` — the OIC/text-dump siblings
carry OPENING between description and receipt (and are single_col), the wide movement
siblings carry PURCHASE/DUMP/M.EXP, and the reduced SALE/CLOSING grids carry the
``===sale===`` banner arrows, so none collide with this token.
"""
from extractors.stock_xlsx.parse_common import cell_text, is_subtotal, to_number

_NIL = {"", "-", "----", "-----"}


def _norm(text):
    return cell_text(text).strip().lower().replace(" ", "")


def _num(value):
    """A nil-aware numeric cell -> canonical string; '-' becomes '0'."""
    if cell_text(value).strip() in _NIL:
        return "0"
    n = to_number(value)
    if n is None:
        return "0"
    if n == int(n):
        return str(int(n))
    return str(n)


def _find_header(rows):
    """Return (group_idx, group_map) for the ITEM DESCRIPTION | RECEIPT | ISSUE | CLOSING row.

    group_map: col-index -> (group_key). group_key in {product, receipt, issue, closing}.
    """
    for idx in range(min(len(rows), 40)):
        cells = [_norm(c) for c in rows[idx]] if rows[idx] else []
        if "itemdescription" in cells and "receipt" in cells and "issue" in cells and "closing" in cells:
            group_map = {}
            for i, c in enumerate(cells):
                if c == "itemdescription":
                    group_map[i] = "product"
                elif c == "receipt":
                    group_map[i] = "receipt"
                elif c == "issue":
                    group_map[i] = "issue"
                elif c == "closing":
                    group_map[i] = "closing"
            return idx, group_map
    return None, None


def detect(rows):
    """Class-B override: the reduced Receipt/Issue/Closing GRID (no opening/purchase)."""
    flat = " ".join(" ".join(str(c) for c in row) for row in rows[:150]).lower().replace(" ", "")
    populated = [row for row in rows[:60] if any(str(c).strip() for c in row)]
    single_col = bool(populated) and all(
        sum(1 for c in row if str(c).strip()) <= 1 for row in populated
    )
    return (
        not single_col
        and "itemdescriptionreceiptissueclosing" in flat
        and "opening" not in flat
        and "purchase" not in flat
        and "m.exp" not in flat
        and "dump" not in flat
        and "===sale===" not in flat
    )


def parse_stock_receipt_issue_closing_grid_xls(rows):
    group_idx, group_map = _find_header(rows)
    if group_idx is None or "product" not in group_map.values():
        return [], {}

    prod_idx = next(i for i, g in group_map.items() if g == "product")
    receipt_idx = next((i for i, g in group_map.items() if g == "receipt"), None)
    issue_idx = next((i for i, g in group_map.items() if g == "issue"), None)
    closing_idx = next((i for i, g in group_map.items() if g == "closing"), None)

    # The CLOSING VALUE column is the physical column immediately to the RIGHT of the
    # CLOSING(qty) column (the two-row header prints "CLOSING" over "QTY. | VALUE"), i.e.
    # the last populated numeric column. Confirm via the sub-header row (group_idx+1),
    # whose cell under that index reads "VALUE".
    value_idx = None
    if closing_idx is not None:
        sub_idx = group_idx + 1
        sub = [_norm(c) for c in rows[sub_idx]] if sub_idx < len(rows) else []
        cand = closing_idx + 1
        if cand < len(sub) and sub[cand] == "value":
            value_idx = cand
        elif cand < len(rows[group_idx + 1 if sub else group_idx]):
            # fall back to the next physical column if the sub-header is absent
            value_idx = cand

    records = []
    for raw_row in rows[group_idx + 1:]:
        cells = [cell_text(c) for c in raw_row] if raw_row else []
        # Skip the sub-header row ("QTY. QTY. QTY. VALUE").
        norms = [_norm(c) for c in cells]
        if norms and set(n for n in norms if n) <= {"qty.", "value", "qty"}:
            continue
        if prod_idx >= len(cells):
            continue
        name = cells[prod_idx].strip()
        if not name or is_subtotal(name):
            continue
        # Skip division band rows: only the product cell is populated (a bare group title
        # like "KLM LAB (COSMOQ)" with every movement column empty).
        non_empty = sum(1 for c in cells if c.strip())
        if non_empty <= 1:
            continue
        # Skip an explicit TOTAL subtotal row (is_subtotal already covers "TOTAL"; keep a
        # defensive check for a leading-space " TOTAL").
        if name.strip().lower().lstrip().startswith("total"):
            continue

        record = {
            "product_name": name,
            "opening_stock": "0",
            "purchase_stock": _num(raw_row[receipt_idx]) if receipt_idx is not None and receipt_idx < len(cells) else "0",
            "sales_qty": _num(raw_row[issue_idx]) if issue_idx is not None and issue_idx < len(cells) else "0",
            "closing_stock": _num(raw_row[closing_idx]) if closing_idx is not None and closing_idx < len(cells) else "0",
        }
        if value_idx is not None and value_idx < len(cells):
            record["closing_stock_value"] = _num(raw_row[value_idx])
        records.append(record)

    detected = {
        "ITEM DESCRIPTION": "product_name",
        "RECEIPT": "purchase_stock",
        "ISSUE": "sales_qty",
        "CLOSING": "closing_stock",
        "VALUE": "closing_stock_value",
    }
    return records, detected
