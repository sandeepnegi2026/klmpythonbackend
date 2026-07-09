"""Marg "STOCK & SALES ANALYSIS" fixed-width TEXT export dumped into a single Excel column.

Some KLM/Marg stockists export this report as plain fixed-width text pasted into column A of an
.xls — every row is one nbsp-padded cell, so the grid-based tabular matcher sees no columns and
extracts 0 rows (UNKNOWN_LAYOUT). Each data line is:

    <product ... pack>   <14 numeric columns>   [<M.EXP  e.g. 3/27>]

Column order (verified: closing = total - sales - free - sample - p/r - repl == 304/304 rows):
    0 OPENING   1 PURCHASE-QTY   2 PURCHASE-FREE   3 S/R-QTY   4 S/R-FREE   5 REPL/OTHER(in)
    6 TOTAL     7 SALES-QTY      8 SALES-FREE      9 SAMPLE    10 P/R-T/F   11 REPL/OTHER(out)
    12 (out)    13 CLOSING

TOTAL(6) = opening + all inflow columns (0..5); CLOSING(13) = TOTAL - all outflow columns (7..12).
So the inflow adjustments (3,4,5) fold into canonical sales_return (they add stock) and the
outflow adjustments (9,10,11,12) fold into purchase_return (they remove it) — with that folding
the canonical sanity equation reconciles exactly. Interleaved "Value in Rs." lines are rupee
subtotals (7 numbers, or a blank product) and are skipped.
"""
import re

from extractors.stock_xlsx.parse_common import cell_text

_NUM_RE = re.compile(r"^-?\d+(?:\.\d+)?$")
_MEXP_RE = re.compile(r"^\d{1,2}/\d{2,4}$")
_NCOLS = 14


def _fold(cols, *idxs):
    """Sum a set of adjustment columns into one canonical field (as a clean numeric string)."""
    total = 0.0
    for i in idxs:
        try:
            total += float(cols[i])
        except (ValueError, IndexError):
            pass
    return str(int(total)) if total == int(total) else str(total)


def parse_marg_stock_analysis_text(rows):
    records = []
    header_seen = False
    for row in rows:
        # Join every cell, not just col 0: the same "STOCK & SALES ANALYSIS" report is
        # also exported as a GRID (2-row split header, qty+free merged into cells like
        # "0    0"). Joining reconstructs the one-line form so the trailing-14 positional
        # read below works identically for both the single-column dump and the grid.
        text = " ".join(cell_text(c) for c in row).replace("\xa0", " ") if row else ""
        stripped = text.strip()
        if not stripped or set(stripped) <= set("-= "):
            continue
        low = stripped.lower()
        if "item description" in low and "opening" in low:
            header_seen = True
            continue
        if not header_seen or low.startswith("value in rs"):
            continue

        toks = stripped.split()
        expiry = toks.pop() if toks and _MEXP_RE.match(toks[-1]) else ""
        nums = []
        while toks and _NUM_RE.match(toks[-1]):
            nums.append(toks.pop())
        nums.reverse()
        if len(nums) < _NCOLS:
            continue  # section title ("KLM COSMO"), a value line, or a blank-product subtotal

        cols = nums[-_NCOLS:]
        # any numerics beyond the 14-column block are trailing product tokens (e.g. "IMXIA 5")
        product = " ".join(toks + nums[:-_NCOLS]).strip()
        if not product or product.lower().startswith("value in rs"):
            continue
        if product.lower() == "quantity":
            continue  # per-group / grand-total subtotal line ("Quantity <14 totals>")

        record = {
            "product_name": product,
            "opening_stock": cols[0],
            "purchase_stock": cols[1],
            "purchase_free": cols[2],
            "sales_return": _fold(cols, 3, 4, 5),
            "total_stock": cols[6],
            "sales_qty": cols[7],
            "sales_free": cols[8],
            "purchase_return": _fold(cols, 9, 10, 11, 12),
            "closing_stock": cols[13],
        }
        if expiry:
            record["expiry"] = expiry
        records.append(record)

    detected = {
        "ITEM DESCRIPTION": "product_name",
        "OPENING STOCK": "opening_stock",
        "PURCHASE QTY.": "purchase_stock",
        "PURCHASE FREE": "purchase_free",
        "S/R (folded)": "sales_return",
        "TOTAL STOCK": "total_stock",
        "SALES QTY.": "sales_qty",
        "SALES FREE": "sales_free",
        "P/R + SAMPLE + REPL (folded)": "purchase_return",
        "CLOSING STOCK": "closing_stock",
    }
    return records, detected
