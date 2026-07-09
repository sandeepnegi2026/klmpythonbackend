"""Marg (ERP9+) "STOCK & SALES ANALYSIS" qty+value fixed-width TEXT export in a single Excel column.

A KLM/Marg family export identical in shape to ``marg_stock_analysis_text`` (plain fixed-width
text pasted into column A of an .xls, so the grid-based tabular matcher sees no columns and
extracts 0 rows) but carrying the *shorter* qty+value block instead of the 14-column movement
block. The header spans two lines::

    ITEM DESCRIPTION            OPENING       RECEIPT       ISSUE        CLOSING     DUMP
    QTY.    VALUE   QTY.  VALUE   QTY.  VALUE   QTY.   VALUE   QTY.

Each data line is ``<product ... pack>`` followed by 9 numeric tokens::

    0 OPENING-QTY   1 OPENING-VALUE
    2 RECEIPT-QTY   3 RECEIPT-VALUE      (RECEIPT == purchase)
    4 ISSUE-QTY     5 ISSUE-VALUE        (ISSUE   == sales)
    6 CLOSING-QTY   7 CLOSING-VALUE
    8 DUMP-QTY      (non-movement damaged/expired qty, OUTSIDE the sanity equation)

So ``CLOSING = OPENING + RECEIPT - ISSUE`` reconciles exactly on every row and every subtotal
(grand total 9427 + 5622 - 4572 = 10477). Bare ``-`` means nil/0. Division bands
(e.g. "KLM COSMO") and per-band / grand ``TOTAL`` lines are interleaved and skipped.

This is the XLSX single-column twin of the PDF sibling ``stock_oric_pairs`` (same qty/value
field mapping) and mirrors ``marg_stock_analysis_text``'s reader mechanics (join every cell with
cell_text, strip \\xa0, skip separator / band / header / "value in rs" / TOTAL lines, gate on
header_seen), reading a trailing 9-column qty+value block instead of 14.
"""
import re

from extractors.stock_xlsx.parse_common import cell_text

_NUM_RE = re.compile(r"^-?\d+(?:\.\d+)?$")
_MEXP_RE = re.compile(r"^\d{1,2}/\d{2,4}$")
_NCOLS = 9


def _is_num_tok(tok):
    """A numeric-column token: a real number, or a standalone dash meaning nil/0.

    Bare ``-`` (or ``-----``) is Marg's nil marker inside a qty/value column. Product codes
    keep their hyphen glued to text (e.g. "HERPIVAL-1G", "NIOSALIC-6"), so a *standalone* dash
    token is never part of a name — it is always a nil cell. Treating it as numeric keeps the
    trailing 9-column run contiguous even when interior columns are nil.
    """
    return bool(_NUM_RE.match(tok)) or set(tok) == {"-"}


def parse_marg_stock_analysis_qv(rows):
    records = []
    header_seen = False
    for row in rows:
        # Join every cell so the reader works whether the report is a true single-column
        # dump (one nbsp-padded cell) or a lightly-gridded variant of the same export.
        text = " ".join(cell_text(c) for c in row).replace("\xa0", " ") if row else ""
        stripped = text.strip()
        if not stripped or set(stripped) <= set("-= "):
            continue  # blank line or a separator rule
        low = stripped.lower()
        if "item description" in low and "opening" in low:
            header_seen = True
            continue
        if not header_seen:
            continue
        if low.startswith("qty.") or low.startswith("value in rs"):
            continue  # the second header line (QTY. VALUE ...) or a rupee subtotal caption

        toks = stripped.split()
        expiry = toks.pop() if toks and _MEXP_RE.match(toks[-1]) else ""
        nums = []
        while toks and _is_num_tok(toks[-1]):
            nums.append(toks.pop())
        nums.reverse()
        # Normalise bare-dash nil markers to "0" so downstream casting reads them as 0.
        nums = ["0" if set(n) == {"-"} else n for n in nums]
        if len(nums) < _NCOLS:
            continue  # a section title ("KLM COSMO") or any non-data line

        cols = nums[-_NCOLS:]
        # Numerics beyond the 9-column block are trailing product tokens (e.g. "IMXIA 5").
        product = " ".join(toks + nums[:-_NCOLS]).strip()
        if not product:
            continue
        plow = product.lower()
        if plow.startswith("value in rs") or plow == "quantity" or plow.startswith("total"):
            continue  # per-group / grand-total subtotal line ("TOTAL <9 totals>")

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
        # cols[8] is DUMP (damaged/expired, non-movement) — kept out of the sanity equation,
        # stashed for reference only.
        dump = cols[8]
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
