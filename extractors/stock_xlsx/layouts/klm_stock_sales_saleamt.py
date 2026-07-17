"""KLM stockist "STOCK & SALES" grid keyed by the SALEAMT/CLOSEAMT/NEAREXP/SAPCODE columns
(TIRUPATI MEDICOSE, "stock_sales.XLS").

Header (single row)::

    NAME | PACK | OPEN | PURCHASE | LASTPERIOD | SALES | SALEAMT | CLOSING | CLOSEAMT | NEAREXP | SAPCODE

The generic `tabular` reader maps the movement columns correctly (closing = OPEN + PURCHASE -
SALES reconciles) BUT (a) binds CLOSEAMT to a throwaway `raw_closeamt` instead of
closing_stock_value, and (b) leaks two kinds of non-product rows that carry a numeric block:
  * per-company **"AMOUNT"** subtotals (SALEAMT / CLOSEAMT column totals, product cell == "AMOUNT");
  * division **bands** "KLM LAB <DIV>" whose PACK is a 3-char division code (KL1/KL2/KLC/KMO...)
    and whose every numeric column is 0 — these look like all-zero products to the generic guard.

"KLM" is a legitimate product brand (KLM D3 / KLM C 1000 / KLM KLIN ...), so the shared parser must
NOT skip it by prefix; this dedicated layout does, because here "KLM LAB " is unambiguously the
manufacturer/division banner. LASTPERIOD (prior-period sales) and SAPCODE are informational.
"""
import re

from extractors.stock_xlsx.parse_common import cell_text, is_subtotal

_NUM_RE = re.compile(r"^-?\d+(?:\.\d+)?$")

# header label (normalised: lowercased, spaces removed) -> canonical field. Only these are kept;
# LASTPERIOD / SAPCODE are dropped.
_HEADER_MAP = {
    "name": "product_name",
    "pack": "pack",
    "open": "opening_stock",
    "purchase": "purchase_stock",
    "sales": "sales_qty",
    "saleamt": "sales_value",
    "closing": "closing_stock",
    "closeamt": "closing_stock_value",
    "nearexp": "expiry",
}


def _norm(text):
    return text.strip().lower().replace(" ", "")


def parse_klm_stock_sales_saleamt(rows):
    # Locate the header row: the one whose cells include NAME + SALEAMT + CLOSEAMT.
    header_idx = None
    col_field = {}
    for idx in range(min(len(rows), 40)):
        cells = [cell_text(c) for c in rows[idx]] if rows[idx] else []
        norms = [_norm(c) for c in cells]
        if "name" in norms and "saleamt" in norms and "closeamt" in norms:
            header_idx = idx
            col_field = {i: _HEADER_MAP[n] for i, n in enumerate(norms) if n in _HEADER_MAP}
            break
    if header_idx is None or "product_name" not in col_field.values():
        return [], {}

    name_idx = next(i for i, f in col_field.items() if f == "product_name")

    records = []
    for raw_row in rows[header_idx + 1:]:
        cells = [cell_text(c) for c in raw_row] if raw_row else []
        if name_idx >= len(cells):
            continue
        name = cells[name_idx].strip()
        if not name:
            continue
        low = name.lower()
        # Skip the "AMOUNT" / "TOTAL AMOUNT" subtotals and any division banner "KLM LAB <div>"
        # (its numeric columns are all zero and its PACK is a division code, never a product).
        if low == "amount" or low.startswith("total") or is_subtotal(name) or low.startswith("klm lab"):
            continue

        record = {}
        for i, field in col_field.items():
            if i < len(cells):
                value = cells[i].strip()
                if field in ("expiry",) and not value:
                    continue
                record[field] = value
        # Default the canonical numeric fields that were blank in this row to "0".
        for field in ("opening_stock", "purchase_stock", "sales_qty", "sales_value",
                      "closing_stock", "closing_stock_value"):
            if not record.get(field):
                record[field] = "0"
        records.append(record)

    detected = {
        "NAME": "product_name",
        "PACK": "pack",
        "OPEN": "opening_stock",
        "PURCHASE": "purchase_stock",
        "SALES": "sales_qty",
        "SALEAMT": "sales_value",
        "CLOSING": "closing_stock",
        "CLOSEAMT": "closing_stock_value",
    }
    return records, detected
