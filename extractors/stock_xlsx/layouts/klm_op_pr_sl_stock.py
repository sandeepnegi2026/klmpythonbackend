"""KLM abbreviated-header "OP_STK / PR_REC / TOT_REC / SL_ISS / CL_STK" stock statement
(.XLS legacy BIFF export — SHREE NATH ENTERPRISE).

Header row (single row, exact abbreviated tokens):
  SR_NO | COMPANY | SAPCODE | PRDNM | PACKING | OP_STK | PR_REC | TOT_REC | SL_ISS |
  CL_STK | RATE | CL_VAL | PKTSTK | AVG_SAL | HSN_CODE

Why a dedicated positional parser (same reasoning as klm_dstk_stock): the ``TOT_REC``
column is a RUNNING TOTAL (TOT_REC = OP_STK + PR_REC on every row — verified), not a
movement. Its header fuzzy-collides with the purchase/receipt synonyms, so the generic
``tabular`` mapper would bind purchase_stock to TOT_REC and double-count receipts, and
every row would fail the sanity equation. We therefore map ONLY the known abbreviated
headers by exact text and deliberately OMIT the running-total / aging / analytics columns
(TOT_REC, PKTSTK, AVG_SAL, SR_NO) so they cannot steal a canonical field.

Reconciles exactly: CL_STK (closing) = OP_STK (opening) + PR_REC (purchase) - SL_ISS
(sales) on 17/17 product rows. No free / scheme-qty column is present in this export.

Leading rows are a section band (vendor / city / "Mfg : ..." / "From : ..." date), each
carrying SR_NO = 0 and all-zero movement columns; a trailing "Total" row also carries
SR_NO = 0. Both are skipped.
"""
from extractors.stock_xlsx.parse_common import cell_text, is_subtotal

# Exact (lowercased, stripped) header text -> canonical field. Everything not listed
# is deliberately omitted so it cannot steal a canonical field:
#   TOT_REC  -> running total (OP_STK + PR_REC); mapping it double-counts receipts.
#   PKTSTK   -> packs-in-stock derived figure.
#   AVG_SAL  -> average-sale analytics.
#   SR_NO    -> serial number.
#   COMPANY  -> division/make code (stamped elsewhere), not a stock quantity.
# SAPCODE is empty in this export while HSN_CODE carries the real HSN, so hsn_code binds
# to HSN_CODE only (SAPCODE stays unmapped).
_COL_MAP = {
    "prdnm": "product_name",
    "packing": "pack",
    "op_stk": "opening_stock",
    "pr_rec": "purchase_stock",
    "sl_iss": "sales_qty",
    "cl_stk": "closing_stock",
    "rate": "rate",
    "cl_val": "closing_stock_value",
    "hsn_code": "hsn_code",
}

# Product-name prefixes that mark a section-band / control row rather than a real product.
_BAND_PREFIXES = (
    "mfg :", "mfg:", "from :", "from:", "to :", "to:",
    "opening value", "closing value", "sales value", "receipt value",
    "grand total", "page total", "company", "division", "manufacturer",
)


def parse_klm_op_pr_sl_stock(rows):
    header_idx = None
    for idx in range(min(len(rows), 60)):
        cells = [cell_text(c).lower().strip() for c in rows[idx]]
        # Unique signature of this KLM export: the OP_STK / PR_REC / TOT_REC / SL_ISS /
        # CL_STK abbreviation set all present on one header row.
        if all(tok in cells for tok in ("op_stk", "pr_rec", "tot_rec", "sl_iss", "cl_stk")):
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
        if any(pl.startswith(k) for k in _BAND_PREFIXES):
            continue
        # Section-band vendor/city rows carry a real name but all movement columns are
        # zero; drop a row only when opening AND purchase AND sales AND closing are all
        # blank/zero (never a genuine stocked product).
        movement = (
            cell_text(record.get("opening_stock", "")).replace(".", "", 1).replace(",", ""),
            cell_text(record.get("purchase_stock", "")).replace(".", "", 1).replace(",", ""),
            cell_text(record.get("sales_qty", "")).replace(".", "", 1).replace(",", ""),
            cell_text(record.get("closing_stock", "")).replace(".", "", 1).replace(",", ""),
        )
        if all(m in {"", "0"} for m in movement):
            continue
        # Skip a stray fully-numeric product cell (page-break artefact).
        if pl.replace(".", "", 1).replace(",", "").isdigit():
            continue
        records.append(record)

    return records, detected
