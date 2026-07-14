"""Marg (ERP9+) "STOCK & SALES ANALYSIS" qty+value TEXT export — OPENING/RECEIPT/ISSUE/CLOSING
only (NO trailing DUMP column), dumped into a single Excel column (BURIMAA MEDICAL AGENCY, KLM .xls).

This is the 8-numeric-column sibling of ``marg_stock_analysis_qv``. Same KLM/Marg family, same
single-column fixed-width text shape (every row is one nbsp-padded cell, so the grid-based
tabular matcher sees no columns and extracts 0 rows -> UNKNOWN_LAYOUT), but the header carries
only four qty+value groups and NO trailing DUMP column::

    ITEM DESCRIPTION            OPENING       RECEIPT       ISSUE        CLOSING
    QTY.    VALUE   QTY.  VALUE   QTY.  VALUE   QTY.   VALUE

Each data line is ``<product ... pack>`` followed by exactly 8 numeric tokens::

    0 OPENING-QTY   1 OPENING-VALUE
    2 RECEIPT-QTY   3 RECEIPT-VALUE   (RECEIPT == purchase inflow)
    4 ISSUE-QTY     5 ISSUE-VALUE     (ISSUE   == sales outflow)
    6 CLOSING-QTY   7 CLOSING-VALUE

So ``CLOSING = OPENING + RECEIPT - ISSUE`` reconciles exactly on every row and every subtotal
(grand total 5018 + 4040 - 4061 = 4997). The file is division-banded (KLM COSMO / COSMOCOR /
COSMOQ / DERMA ...) with per-band and grand ``TOTAL`` lines and page-break repeats of the
header ("Continued" / "Page" / re-printed ITEM DESCRIPTION header) — all interleaved and skipped.

The trailing pack token (30GM, 10S', 60ML, ...) is peeled into ``pack`` like the BALLRI grid
sibling ``marg_sale_closing_grid_xlsx``. Because the export carries NO DUMP column this is a
strict 8-column read; the DUMP-bearing 9-column variant stays on ``marg_stock_analysis_qv`` (the
detect gate here requires "dump" NOT in the flat text, keeping the two disjoint), and the
14-column movement sibling ``marg_stock_analysis_text`` is excluded by its "m.exp" column.
"""
import re

from extractors.stock_xlsx.parse_common import cell_text

_NUM_RE = re.compile(r"^-?\d+(?:\.\d+)?$")
_MEXP_RE = re.compile(r"^\d{1,2}/\d{2,4}$")
_NCOLS = 8


def _is_num_tok(tok):
    """A numeric-column token: a real number, or a standalone dash meaning nil/0.

    Bare ``-`` is Marg's nil marker inside a qty/value column; product codes keep their hyphen
    glued to text (e.g. "ZYDIP-C", "NIOSALIC 6"), so a standalone dash is always a nil cell.
    """
    return bool(_NUM_RE.match(tok)) or set(tok) == {"-"}


def _split_name_pack(text):
    """Peel the fixed-width Pack column (last token) from the single product string.

    The pack is a unit token (30GM / 10S' / 60ML / 2ML). Only peel a last token that is NOT a
    bare number, so a stray numeric that leaked from the name is never mistaken for a pack.
    """
    toks = text.split()
    if len(toks) <= 1:
        return text, ""
    if _NUM_RE.match(toks[-1]):
        return text, ""
    return " ".join(toks[:-1]), toks[-1]


def parse_marg_stock_open_rcpt_issue_xls(rows):
    records = []
    header_seen = False
    # D.D. ENTERPRISE ships the DUMP-bearing export whose 'DUMP' group caption is truncated off
    # the header, leaving an orphan 9th 'QTY.' on the sub-header line. Its data rows carry 8
    # movement numbers + a trailing DUMP qty; taking nums[-8:] would shift every field one slot
    # left. When the orphan 'QTY.' is present, read the FIRST 8 (movement) and stash the DUMP.
    orphan_dump = False
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
            continue  # address / phone / GSTIN / title banner above the first header
        if low.startswith("qty.") or low.startswith("value in rs"):
            # sub-header "QTY. VALUE ... QTY." — an extra trailing QTY. (more QTY than VALUE
            # tokens) is the truncated DUMP column caption.
            if low.startswith("qty.") and low.count("qty") > low.count("value"):
                orphan_dump = True
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
            continue  # a section title ("KLM COSMO"), "Continued"/"Page", or any non-data line

        dump = None
        if orphan_dump:
            # trailing run = 8 movement numbers + optional DUMP; any leading extras are
            # name digits that glued onto the numeric run.
            move_len = 9 if len(nums) >= 9 else 8
            lead = nums[: len(nums) - move_len]
            movement = nums[len(nums) - move_len:]
            cols = movement[:_NCOLS]
            dump = movement[_NCOLS] if len(movement) > _NCOLS else None
            product_full = " ".join(toks + lead).strip()
        else:
            cols = nums[-_NCOLS:]
            # Numerics beyond the 8-column block are trailing product tokens (e.g. "IMXIA 5").
            product_full = " ".join(toks + nums[:-_NCOLS]).strip()
        if not product_full:
            continue
        plow = product_full.lower()
        if plow.startswith("value in rs") or plow == "quantity" or plow.startswith("total"):
            continue  # per-band / grand-total subtotal line ("TOTAL <8 totals>")

        name, pack = _split_name_pack(product_full)
        record = {
            "product_name": name,
            "pack": pack,
            "opening_stock": cols[0],
            "opening_value": cols[1],
            "purchase_stock": cols[2],   # RECEIPT qty
            "purchase_value": cols[3],   # RECEIPT value
            "sales_qty": cols[4],        # ISSUE qty
            "sales_value": cols[5],      # ISSUE value
            "closing_stock": cols[6],
            "closing_stock_value": cols[7],
        }
        if dump not in (None, "", "-", "0", "0.0"):
            record.setdefault("extra_data", {})["dump_qty"] = dump
        if expiry:
            record["expiry"] = expiry
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
