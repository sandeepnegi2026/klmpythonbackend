"""Marg "wide" Stock & Sales grid — a 2-row banded movement header.

    group row :  ITEM DESCRIPTION | OPENING | SALE  REPL./  TOTAL | PURCHASE REPL./ | CLOSING ...
    sub row   :  (blank)          | STOCK   | PURCHASES RETURN OTHERS STOCK SALES RETURN OTHERS STOCK | RATE | "<MON> M.EXP"
    data      :  AMOCLAFIX 625 10 | 32 | 0 0 0 32 | 30 0 0 | 2 | 131.66 | 0  8/27

The generic ``tabular`` path locks ``detect_header_row`` onto the GROUP row, whose merged
labels (at cols 1,3,4,5,7,8,9) do not align with the real data columns the SUB row defines,
so the movement columns are mis-read and every row fails sanity.

The 9 movement sub-columns are, by position after the product column:
  c1 STOCK(opening) c2 PURCHASES c3 RETURN c4 OTHERS c5 STOCK(=TOTAL, derived)
  c6 SALES c7 RETURN c8 OTHERS c9 STOCK(closing)  [c10 RATE, c11 "<MON> M.EXP"]

The REPL./RETURN/OTHERS columns are *replacements that move with* the inflow/outflow band
(additive to purchases on the left, additive to sales on the right) — the OPPOSITE sign of
canonical purchase_return/sales_return — so we FOLD them into purchase/sales rather than map
them to the return fields. Then closing = opening + purchase − sales reconciles exactly
(verified: c5 == c1+c2+c3+c4 on every row, confirming c5 is TOTAL and c9 is closing).
"""
from extractors.stock_xlsx.layouts.marg_erp9_movement import _MEXP_RE, _lead_number
from extractors.stock_xlsx.parse_common import cell_text, is_subtotal

_SUB_SEQ = ["STOCK", "PURCHASES", "RETURN", "OTHERS", "STOCK", "SALES", "RETURN", "OTHERS", "STOCK"]


def _find_band(rows):
    """Return (sub_row_index, [9 movement column indices]) for the wide band, else (None, None)."""
    for i in range(1, min(40, len(rows))):
        cells = [cell_text(c).upper() for c in rows[i]]
        non_empty = [(j, c) for j, c in enumerate(cells) if c]
        labels = [c for _, c in non_empty]
        if labels[:9] == _SUB_SEQ:
            grp = " ".join(cell_text(c).upper() for c in rows[i - 1])
            if "OPENING" in grp and "CLOSING" in grp and "PURCHASE" in grp and "SALE" in grp:
                cols = [j for j, _ in non_empty[:9]]
                return i, cols
    return None, None


def _is_section_row(raw_row):
    non_empty = [cell_text(c) for c in raw_row if cell_text(c)]
    return len(non_empty) >= 2 and len(set(non_empty)) == 1


def parse_marg_stock_sale_band(rows):
    sub_idx, cols = _find_band(rows)
    if sub_idx is None:
        return [], {}
    c1, c2, c3, c4, c5, c6, c7, c8, c9 = cols

    def num(raw_row, idx):
        return (_lead_number(raw_row[idx]) if idx < len(raw_row) else None) or 0.0

    records = []
    for raw_row in rows[sub_idx + 1:]:
        if not any(raw_row):
            continue
        if _is_section_row(raw_row):
            continue
        product = cell_text(raw_row[0]) if raw_row else ""
        if not product or is_subtotal(product):
            continue
        pl = product.lower().strip()
        if pl.startswith((
            "company", "division", "manufacturer", "item name", "item description",
            "product name", "value", "quantity", "total",
        )):
            continue
        if pl.replace(".", "", 1).replace(",", "").isdigit():
            continue
        if sum(1 for c in raw_row if cell_text(c)) <= 1:
            continue

        record = {
            "product_name": product,
            "opening_stock": num(raw_row, c1),
            "purchase_stock": num(raw_row, c2) + num(raw_row, c3) + num(raw_row, c4),
            "sales_qty": num(raw_row, c6) + num(raw_row, c7) + num(raw_row, c8),
            "closing_stock": num(raw_row, c9),
        }
        # optional expiry from the trailing "<MON> M.EXP" column, e.g. "0  8/27"
        tail = cols[-1] + 2
        if tail < len(raw_row):
            mexp = _MEXP_RE.search(cell_text(raw_row[tail]))
            if mexp:
                record["expiry"] = mexp.group(1)
        records.append(record)

    detected = {
        "ITEM DESCRIPTION": "product_name",
        "OPENING": "opening_stock",
        "PURCHASE": "purchase_stock",
        "SALE": "sales_qty",
        "CLOSING": "closing_stock",
    }
    return records, detected
