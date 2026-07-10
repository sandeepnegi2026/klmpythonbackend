"""Marg (ERP9+) "STOCK & SALES ANALYSIS" qty+value single-column TEXT dump — OPENING/RECEIPT/
ISSUE/CLOSING + DUMP + a trailing extra column, exported to .xlsx as a MERGED single cell that
the reader unmerges into many IDENTICAL columns (D.S.PHARMA, "KKIK.xlsx").

Same KLM/Marg family as ``marg_stock_analysis_qv`` but two differences:
  1. the fixed-width text row is stored as ONE merged cell spanning the sheet width, so after the
     xlsx unmerge every physical column holds the SAME string (the grid matchers see 16 non-empty
     cells and mis-route it). We collapse the duplicates back to the single logical line.
  2. the trailing block is 10 numbers, not 9 — OPENING/RECEIPT/ISSUE/CLOSING (qty+value) followed
     by DUMP qty AND one further analytics column (APR / re-order). Only the first 8 are canonical.

Each data line (after de-duplication) is ``<product ... pack unit>`` then 10 numeric tokens::

    0 OPENING-QTY   1 OPENING-VALUE
    2 RECEIPT-QTY   3 RECEIPT-VALUE   (RECEIPT == purchase)
    4 ISSUE-QTY     5 ISSUE-VALUE     (ISSUE   == sales)
    6 CLOSING-QTY   7 CLOSING-VALUE
    8 DUMP-QTY  (damaged/expired, non-movement)   9 extra (analytics, ignored)

So ``CLOSING = OPENING + RECEIPT - ISSUE`` reconciles (grand total 1627 + 409 - 542 = 1494). The
book is division-banded ("KLM LAB (PEDIA DIV.)" ...) with per-band ``TOTAL`` lines and APPENDS a
SUPPLIER register (rows whose block is a date/amount, not a 10-number movement line) — all fail
the >=10-number gate and are skipped. Bare ``-`` is Marg's nil marker.
"""
import re

from extractors.stock_xlsx.parse_common import cell_text, is_subtotal

_NUM_RE = re.compile(r"^-?\d+(?:\.\d+)?$")
_MEXP_RE = re.compile(r"^\d{1,2}/\d{2,4}$")
_NCOLS = 10  # OPENING/RECEIPT/ISSUE/CLOSING qty+value (8) + DUMP qty + trailing extra


def _is_num_tok(tok):
    return bool(_NUM_RE.match(tok)) or set(tok) == {"-"}


def _row_text(row):
    """Collapse the merged-cell duplicates: join the DISTINCT non-empty cell strings.

    A merged single-column line unmerges into N identical cells, so the distinct set is one
    string — the original line. (A genuinely multi-column row would keep its distinct cells, but
    this layout is only reached for the replicated single-column export.)
    """
    seen = []
    for c in row:
        t = cell_text(c).strip()
        if t and t not in seen:
            seen.append(t)
    return " ".join(seen).replace("\xa0", " ")


def parse_marg_stock_analysis_qv_dumpext(rows):
    records = []
    header_seen = False
    for row in rows:
        stripped = _row_text(row).strip() if row else ""
        if not stripped or set(stripped) <= set("-= "):
            continue
        low = stripped.lower()
        if "item description" in low and "opening" in low:
            header_seen = True
            continue
        if not header_seen:
            continue
        if low.startswith("qty.") or low.startswith("value in rs") or low.startswith("supplier"):
            continue

        toks = stripped.split()
        expiry = toks.pop() if toks and _MEXP_RE.match(toks[-1]) else ""
        nums = []
        while toks and _is_num_tok(toks[-1]):
            nums.append(toks.pop())
        nums.reverse()
        nums = ["0" if set(n) == {"-"} else n for n in nums]
        if len(nums) < _NCOLS:
            continue  # band ("KLM LAB (PEDIA DIV.)"), TOTAL (9 nums), supplier register, footer

        cols = nums[-_NCOLS:]
        product = " ".join(toks + nums[:-_NCOLS]).strip()
        if not product:
            continue
        plow = product.lower()
        if is_subtotal(product) or plow.startswith("total") or plow == "quantity":
            continue

        record = {
            "product_name": product,
            "opening_stock": cols[0],
            "opening_value": cols[1],
            "purchase_stock": cols[2],   # RECEIPT qty
            "purchase_value": cols[3],   # RECEIPT value
            "sales_qty": cols[4],        # ISSUE qty
            "sales_value": cols[5],      # ISSUE value
            "closing_stock": cols[6],
            "closing_stock_value": cols[7],
        }
        dump = cols[8]                   # cols[9] is the trailing analytics column (ignored)
        if dump not in ("", "-", "0", "0.0"):
            record.setdefault("extra_data", {})["dump_qty"] = dump
        if expiry:
            record["expiry"] = expiry
        records.append(record)

    detected = {
        "ITEM DESCRIPTION": "product_name",
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
