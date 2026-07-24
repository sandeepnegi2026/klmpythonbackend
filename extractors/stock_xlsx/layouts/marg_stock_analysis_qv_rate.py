"""Marg (ERP9+) "STOCK & SALES ANALYSIS" qty+value TEXT dump WITH a leading RATE column —
the 10-numeric-column single-column twin of ``marg_stock_analysis_qv_grid`` (DIKSHA) and the
RATE sibling of ``marg_stock_analysis_qv`` (BIVIC ENTERPRISES, KLM JUNE.XLS).

Same KLM/Marg family as ``marg_stock_analysis_qv``: fixed-width text pasted into column A of an
.xls, so the grid-based ``tabular`` matcher sees no columns and extracts 0 rows. Two-line header::

    ITEM DESCRIPTION            RATE       OPENING       RECEIPT       ISSUE       CLOSING     DUMP
                               (RATE)  QTY.  VALUE  QTY.  VALUE  QTY.  VALUE  QTY.  VALUE  QTY.

Each data line is ``<product ... pack>`` followed by exactly 10 numeric tokens::

    0 RATE          (per-unit price, informational — NOT part of the sanity equation)
    1 OPENING-QTY   2 OPENING-VALUE
    3 RECEIPT-QTY   4 RECEIPT-VALUE      (RECEIPT == purchase)
    5 ISSUE-QTY     6 ISSUE-VALUE        (ISSUE   == sales)
    7 CLOSING-QTY   8 CLOSING-VALUE
    9 DUMP-QTY      (damaged/expired, OUTSIDE the sanity equation)

So ``CLOSING = OPENING + RECEIPT - ISSUE`` reconciles exactly on every row.  Bare ``-`` means
nil/0.  Division bands (e.g. "KLM COSMO"), the second header line ("QTY. VALUE ..."), separator
rules and per-band / grand ``TOTAL`` lines are interleaved and skipped.

Why a separate layout (not the ``has_rate`` branch of ``marg_stock_analysis_qv``): that branch
was written for the R.K.MEDICOS variant which additionally prints a trailing CHAL column, so it
hardwires ``ncols = 11`` and drops every row of this RATE-but-no-CHAL export (10 columns).  This
parser reads the trailing 10-column block, anchored on the RIGHT so the RATE prefix and the DUMP
suffix land in fixed slots, and folds RECEIPT->purchase / ISSUE->sales exactly like its grid twin.
"""
import re

from extractors.stock_xlsx.parse_common import cell_text

_NUM_RE = re.compile(r"^-?\d+(?:\.\d+)?$")
_MEXP_RE = re.compile(r"^\d{1,2}/\d{2,4}$")
_NCOLS = 10  # RATE + OPENING(Q,V) + RECEIPT(Q,V) + ISSUE(Q,V) + CLOSING(Q,V) + DUMP


def _is_num_tok(tok):
    """A numeric-column token: a real number, or a standalone dash meaning nil/0.

    Bare ``-`` (or ``-----``) is Marg's nil marker inside a qty/value column. Product codes keep
    their hyphen glued to text (e.g. "HERPIVAL-1G"), so a *standalone* dash token is never part of
    a name — it is always a nil cell. Treating it as numeric keeps the trailing 10-column run
    contiguous even when interior columns are nil.
    """
    return bool(_NUM_RE.match(tok)) or set(tok) == {"-"}


def parse_marg_stock_analysis_qv_rate(rows):
    records = []
    header_seen = False
    for row in rows:
        # Join every cell so the reader works whether the report is a true single-column dump
        # (one nbsp-padded cell) or a lightly-gridded variant of the same export.
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
        # Numerics beyond the 10-column block are trailing product tokens (e.g. "IMXIA 5").
        product = " ".join(toks + nums[:-_NCOLS]).strip()
        if not product:
            continue
        plow = product.lower()
        if plow.startswith("value in rs") or plow == "quantity" or plow.startswith("total"):
            continue  # per-group / grand-total subtotal line ("TOTAL <10 totals>")

        record = {
            "product_name": product,
            "rate": cols[0],
            "opening_stock": cols[1],
            "opening_value": cols[2],
            "purchase_stock": cols[3],   # RECEIPT qty
            "purchase_value": cols[4],   # RECEIPT value
            "sales_qty": cols[5],        # ISSUE qty
            "sales_value": cols[6],      # ISSUE value
            "closing_stock": cols[7],
            "closing_stock_value": cols[8],
        }
        # DUMP (damaged/expired, non-movement) — kept OUT of the sanity equation, stashed for
        # reference only.
        dump = cols[9]
        if dump not in ("", "-", "0", "0.0"):
            record.setdefault("extra_data", {})["dump_qty"] = dump
        if expiry:
            record["expiry"] = expiry
        records.append(record)

    detected = {
        "ITEM DESCRIPTION": "product_name",
        "RATE": "rate",
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
