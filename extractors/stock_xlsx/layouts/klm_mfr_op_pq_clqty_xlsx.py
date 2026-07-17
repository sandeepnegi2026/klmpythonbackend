"""KLM "MFR Wise Stock and Sales" abbreviated Op/PQ/Fr/SQ/.../Cl Qty export
(SHRI JAYANTHI PHARMA PVT LTD — Klm Stock and Sales From 01-06-26 To 30-06-26.xls,
an .xlsx workbook carrying an .xls extension).

Single header row (row index 2), exact tokens:
  Product Name | Packing | Op | PQ | Fr | Rp | SQ | Fr1 | Rp2 | SR | PR | Adj | ST |
  Cl Qty | Order | LM | Exp | Code

Why a dedicated positional parser: the generic ``tabular`` header mapper binds only
Op->opening_stock and Cl Qty->closing_stock. It leaves PQ/Fr/SQ/Fr1/Rp2/SR/Adj/LM
unbound (raw_*) and, worse, mis-binds PR->rate, ST->gst_rate, Rp->mrp. With the sole
inflow (PQ) and the sales column (SQ) dropped, closing never reconciles, and the 72
per-division value-footer rows leak in as phantom records (opening_stock = the money
value), auto-failing sanity.

This parser maps ONLY the known abbreviated headers by exact text:
  Product Name -> product_name
  Packing      -> pack
  Op           -> opening_stock
  PQ           -> purchase_stock       (the sole inflow)
  Fr           -> purchase_free
  SQ           -> sales_qty
  Fr1          -> sales_free
  SR           -> sales_return
  PR           -> purchase_return
  Adj          -> signed adjustment    (+ folds into sales_return, - into
                  purchase_return, same convention as klm_stock_and_sale)
  ST           -> stock-transfer OUT   (subtracts from closing; folded into sales_free)
  Cl Qty       -> closing_stock

Deliberately OMITTED so they cannot steal a canonical field: Rp / Rp2 (rates), LM
(last-month sales), Order (pending order), Exp (expiry date), Code (product code).

Reconciles (this file): Cl Qty = Op + PQ + Fr - SQ - Fr1 + SR - PR + Adj - ST holds on
230/230 product rows. Column sums Op 1,368 + PQ 846 + Fr 0 - SQ 895 - Fr1 0 + SR 10
- PR 10 + Adj 0 - ST 0 = 1,319 = Cl Qty 1,319 (Fr/Fr1/Adj/ST all zero in this export).

Rows are grouped into 8 KLM division bands 'KLM LABORATORIES PVT LTD (<DIV>)  (<code>)';
each band is closed by 9 value-footer rows (Open Stock Value / Purchase Value / Sale
Value / ST Value / (May) Sale Value / (Apr) Sale Value / Sale Return Value / Purchase
Return Value / Closing Stock Value), which carry only a label in col 0 and a money value
in col 2 (Code cell empty). Product rows always carry a non-empty numeric Code column, so
band + footer + blank-separator rows are dropped by requiring a Code cell.
"""
from extractors.stock_xlsx.parse_common import cell_text

# Exact (lowercased, space-stripped) header text -> canonical field. Everything not
# listed is deliberately omitted so it cannot steal a canonical field.
_COL_MAP = {
    "productname": "product_name",
    "packing":     "pack",
    "op":          "opening_stock",
    "pq":          "purchase_stock",
    "fr":          "purchase_free",
    "sq":          "sales_qty",
    "fr1":         "sales_free",
    "sr":          "sales_return",
    "pr":          "purchase_return",
    "clqty":       "closing_stock",
    # "adj" and "st" handled specially (signed folds) — see below.
    # "rp"/"rp2" (rates), "lm", "order", "exp", "code" intentionally omitted.
}

_HEADER_TOKENS = ("op", "pq", "fr", "sq", "fr1", "rp2", "clqty")


def _norm(cell):
    return cell_text(cell).lower().replace(" ", "")


def _num(cell):
    text = cell_text(cell)
    if text in ("", "-"):
        return 0.0
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return 0.0


def parse_klm_mfr_op_pq_clqty_xlsx(rows):
    header_idx = None
    adj_col = st_col = code_col = None
    for idx in range(min(len(rows), 60)):
        cells = [_norm(c) for c in rows[idx]]
        if all(tok in cells for tok in _HEADER_TOKENS):
            header_idx = idx
            break
    if header_idx is None:
        return [], {}

    col_to_canonical = {}
    detected = {}
    for i, cell in enumerate(rows[header_idx]):
        key = _norm(cell)
        if key == "adj":
            adj_col = i
            continue
        if key == "st":
            st_col = i
            continue
        if key == "code":
            code_col = i
            continue
        canonical = _COL_MAP.get(key)
        if canonical and canonical not in col_to_canonical.values():
            col_to_canonical[i] = canonical
            detected[cell_text(cell)] = canonical

    if (
        "product_name" not in col_to_canonical.values()
        or "closing_stock" not in col_to_canonical.values()
        or code_col is None
    ):
        return [], {}

    records = []
    for raw_row in rows[header_idx + 1:]:
        if not any(cell_text(c) for c in raw_row):
            continue
        product = cell_text(raw_row[0]) if raw_row else ""
        # Product rows always carry a numeric Code; division bands
        # ('KLM LABORATORIES PVT LTD (...)') and the 9 value-footer rows
        # (Open Stock Value / ... / Closing Stock Value) have an empty Code cell.
        code = cell_text(raw_row[code_col]) if code_col < len(raw_row) else ""
        if not product or not code:
            continue

        record = {}
        for col_idx, key in col_to_canonical.items():
            if col_idx < len(raw_row):
                record[key] = raw_row[col_idx]

        # Fold ST (stock-transfer OUT) into sales_free: it subtracts from closing exactly
        # like an outflow, matching the ERP's Cl = Op + PQ + Fr - SQ - Fr1 + SR - PR
        # + Adj - ST equation. Additive with any Fr1 already present.
        if st_col is not None and st_col < len(raw_row):
            st_out = _num(raw_row[st_col])
            if st_out:
                base = _num(record.get("sales_free", 0)) + st_out
                record["sales_free"] = base if base == int(base) else base

        # Fold signed Adj: positive -> sales_return (inflow), negative -> purchase_return
        # (outflow), same convention as klm_stock_and_sale StkAdj.
        if adj_col is not None and adj_col < len(raw_row):
            adj = _num(raw_row[adj_col])
            if adj > 0:
                base = _num(record.get("sales_return", 0)) + adj
                record["sales_return"] = base
            elif adj < 0:
                base = _num(record.get("purchase_return", 0)) + abs(adj)
                record["purchase_return"] = base

        record["product_name"] = product
        records.append(record)

    return records, detected
