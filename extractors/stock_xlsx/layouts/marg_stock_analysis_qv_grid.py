"""Marg (ERP9+) "STOCK & SALES ANALYSIS" qty+value GRID — OPENING/RECEIPT/ISSUE/CLOSING + DUMP,
as a clean column-aligned .xls grid (DERMA DISTRIBUTORS, KLM "ALL DIVISION STOCK STATEMENT").

This is the GRID twin of the single-column ``marg_stock_analysis_qv`` text dump: same KLM/Marg
report and the same qty+value block WITH a trailing DUMP column, but every value sits in its own
physical column, so we read it POSITIONALLY by index. Two-row header::

    (row A)  ITEM DESCRIPTION | OPENING |      | RECEIPT |      | ISSUE |      | CLOSING |      | DUMP |
    (row B)                   | QTY.    | VALUE| QTY.    | VALUE| QTY.  | VALUE| QTY.    | VALUE| QTY. | APR N/EXP

so the physical columns are::

    col0  ITEM DESCRIPTION  (product text + trailing pack token -> product_name, peel pack)
    col1  OPENING QTY       -> opening_stock          col2  OPENING VALUE  -> opening_value
    col3  RECEIPT QTY       -> purchase_stock         col4  RECEIPT VALUE  -> purchase_value
    col5  ISSUE QTY         -> sales_qty              col6  ISSUE VALUE    -> sales_value
    col7  CLOSING QTY       -> closing_stock          col8  CLOSING VALUE  -> closing_stock_value
    col9  DUMP QTY          (damaged/expired, OUTSIDE the sanity equation)
    col10 APR N/EXP         (prior-month analytics, ignored)

``CLOSING = OPENING + RECEIPT - ISSUE`` reconciles on every row (7 + 10 - 10 = 7).

The book is division-banded (KLM COSMO / KLM DERMA / KLM GYNEC ...) with page-break repeats of
the "DERMA DISTRIBUTORS" / "STOCK & SALES ANALYSIS" / "ITEM DESCRIPTION" header block, and it
APPENDS an unrelated SUPPLIER / DEBIT-NOTE ledger after the stock grand total (rows whose col1 is
a DATE, not a quantity). All of those — bands, page titles, ``TOTAL`` subtotals, the supplier
ledger and the MARG footer — carry a col0 label but leave the OPENING/CLOSING qty cells blank (or
a date), so gating on "col1 AND col7 are numeric-or-nil-dash" drops every one of them while
keeping real products (including zero-stock rows printed as bare "-" and legitimate product names
that start with "KLM ", e.g. "KLM C-20 GEL"). This is what stops the trailing phantom rows
("STOCK & SALES ANALYSIS", "PARTH MEDISALES") the generic `tabular` reader emitted.
"""
import re

from extractors.stock_xlsx.constants import SUBTOTAL_RE
from extractors.stock_xlsx.parse_common import cell_text

_NUM_RE = re.compile(r"^-?\d+(?:\.\d+)?$")

# Fixed positional column map (0-based).
_OPEN_Q, _OPEN_V = 1, 2
_RECV_Q, _RECV_V = 3, 4
_ISSUE_Q, _ISSUE_V = 5, 6
_CLOSE_Q, _CLOSE_V = 7, 8
_DUMP_Q = 9


def _num_or_nil(tok):
    """Return the clean numeric string for a qty/value cell, or None if the cell is not a
    quantity (blank, a text label, or a date like '02-04-2026'). Bare '-' means nil -> '0'."""
    tok = tok.strip()
    if not tok:
        return None
    if set(tok) == {"-"}:
        return "0"
    return tok if _NUM_RE.match(tok) else None


def _split_name_pack(text):
    """Peel the trailing pack token (last whitespace token) unless it is a bare number."""
    toks = text.split()
    if len(toks) <= 1:
        return text, ""
    if _NUM_RE.match(toks[-1]):
        return text, ""
    return " ".join(toks[:-1]), toks[-1]


def parse_marg_stock_analysis_qv_grid(rows):
    # Locate the first header row: col0 == 'ITEM DESCRIPTION'.
    header_idx = None
    for idx in range(min(len(rows), 60)):
        first = cell_text(rows[idx][0]) if rows[idx] else ""
        if first.strip().lower().replace(" ", "") == "itemdescription":
            header_idx = idx
            break
    if header_idx is None:
        return [], {}

    # DIKSHA sibling: an extra RATE column sits between ITEM DESCRIPTION and the
    # OPENING block, shifting every movement column one to the right. Derive the
    # shift from where the 'OPENING' label actually sits in the header row (the
    # base DERMA grid has it at col1 -> shift 0, so its parse is unchanged).
    shift = 0
    for j, c in enumerate(rows[header_idx]):
        if "opening" in cell_text(c).strip().lower():
            shift = j - _OPEN_Q
            break

    records = []
    for raw_row in rows[header_idx + 1:]:
        cells = [cell_text(c) for c in raw_row] if raw_row else []
        if len(cells) <= _CLOSE_V + shift:
            continue  # a short line (page title / company banner) — no movement columns
        name_cell = cells[0].strip()
        if not name_cell or SUBTOTAL_RE.match(name_cell):
            continue  # blank line or a 'Total' subtotal
        low = name_cell.lower().replace(" ", "")
        if low in {"itemdescription"} or low.startswith("suppliername"):
            continue  # repeated page header / start of the appended supplier ledger

        # The sole structural gate: a real product row prints a numeric (or bare-dash nil)
        # OPENING and CLOSING quantity. Bands, page titles, TOTAL lines, and the supplier /
        # debit-note ledger (col1 is a DATE) all fail this and are dropped.
        opening = _num_or_nil(cells[_OPEN_Q + shift])
        closing = _num_or_nil(cells[_CLOSE_Q + shift])
        if opening is None or closing is None:
            continue

        name, pack = _split_name_pack(name_cell)
        record = {
            "product_name": name,
            "pack": pack,
            "opening_stock": opening,
            "opening_value": _num_or_nil(cells[_OPEN_V + shift]) or "0",
            "purchase_stock": _num_or_nil(cells[_RECV_Q + shift]) or "0",
            "purchase_value": _num_or_nil(cells[_RECV_V + shift]) or "0",
            "sales_qty": _num_or_nil(cells[_ISSUE_Q + shift]) or "0",
            "sales_value": _num_or_nil(cells[_ISSUE_V + shift]) or "0",
            "closing_stock": closing,
            "closing_stock_value": _num_or_nil(cells[_CLOSE_V + shift]) or "0",
        }
        dump = _num_or_nil(cells[_DUMP_Q + shift]) if len(cells) > _DUMP_Q + shift else None
        if dump not in (None, "0", "0.0"):
            record.setdefault("extra_data", {})["dump_qty"] = dump
        records.append(record)

    detected = {
        "ITEM DESCRIPTION": "product_name",
        "PACK": "pack",
        "OPENING QTY.": "opening_stock",
        "OPENING VALUE": "opening_value",
        "RECEIPT QTY.": "purchase_stock",
        "RECEIPT VALUE": "purchase_value",
        "ISSUE QTY.": "sales_qty",
        "ISSUE VALUE": "sales_value",
        "CLOSING QTY.": "closing_stock",
        "CLOSING VALUE": "closing_stock_value",
    }
    return records, detected
