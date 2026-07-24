"""KLM/Marg "STOCK & SALES ANALYSIS" simple OPENING/RECEIPT/ISSUE/CLOSING text dump.

AMETOMBI SALES AGENCIES exports the KLM "STOCK & SALES ANALYSIS" report as a plain
fixed-width TEXT report pasted into column A of an .xls, so every row is one nbsp-padded
single cell (`load_data_sheets` yields single-column rows). Unlike the 14-column movement
sibling (`marg_stock_analysis_text`) or the 8/9-column qty+value dumps
(`marg_stock_open_rcpt_issue_xls` / `marg_stock_analysis_qv`), this reduced export carries
ONLY four numeric movement columns under::

    ITEM DESCRIPTION                 OPENING   RECEIPT     ISSUE   CLOSING M.EXP

so `marg_stock_analysis_text` (which requires 14 trailing numbers) drops every row -> 0 rows.

Each data line is::

    <product ... [pack]>   OPENING   RECEIPT   ISSUE   CLOSING   [M.EXP e.g. 3/27]

Map (verified: closing = opening + receipt - issue on 100% of rows across both books):

    OPENING  -> opening_stock
    RECEIPT  -> purchase_stock
    ISSUE    -> sales_qty
    CLOSING  -> closing_stock

'-' means nil (0). A stray packing token (a bare count like "1", an "N*M" strip like
"1*10", or an "N-M" band) can sit between the description and the four numbers; it is peeled
into `pack` so the product name stays clean. The trailing "M.EXP" (nearest-expiry, `mm/yy`)
is captured as `expiry`, outside the sanity equation.

The report is division-banded (bare "KLM COSMO" / "KLM DERMA" / "KLM PEDIA" title lines) with
"TOTAL <4 numbers>" subtotals and a trailing supplier ledger. Real products also start with
"KLM " (e.g. "KLM C 20 SERUM 15ML", "KLM-D3 60K CAP"), so bands are NOT skipped by prefix:
the sole structural gate is "the line ends in four numeric-or-nil movement tokens" -- band
title lines carry none and are dropped, while `SUBTOTAL_RE` removes the TOTAL lines.
"""
import re

from extractors.stock_xlsx.constants import SUBTOTAL_RE

_NUM_RE = re.compile(r"^-?\d+(?:\.\d+)?$")
_NIL_RE = re.compile(r"^-+$")
_MEXP_RE = re.compile(r"^\d{1,2}/\d{2,4}$")
# A stray packing-column token stuck between the description and the numbers: a bare count
# ("1", "10"), an "N*M" strip ("1*10", "1*15"), or an "N-M" band ("1-10"). Unit-suffixed
# tokens ("60ML", "30G") are genuine name descriptors and are left for the pipeline pack
# extractor, so they are deliberately NOT matched here.
_PACK_RE = re.compile(r"^\d+(?:[*\-x]\d+)?$")
_NCOLS = 4


def _num_or_nil(tok):
    if _NIL_RE.match(tok):
        return "0"
    return tok if _NUM_RE.match(tok) else None


def parse_stock_sales_analysis_oic_xlsx(rows):
    records = []
    header_seen = False
    for row in rows:
        text = " ".join(str(c) for c in row).replace("\xa0", " ") if row else ""
        stripped = re.sub(r" +", " ", text).strip()
        if not stripped or set(stripped) <= set("-= "):
            continue
        low = stripped.lower()
        if "item description" in low and "opening" in low:
            header_seen = True
            continue
        if not header_seen or SUBTOTAL_RE.match(stripped):
            continue

        toks = stripped.split()
        expiry = toks.pop() if toks and _MEXP_RE.match(toks[-1]) else ""

        # The four movement columns are the LAST four numeric-or-nil tokens; anything before
        # them is the product description (plus an optional stray packing token).
        movement = []
        rest = toks[:]
        while rest and len(movement) < _NCOLS and (
            _NUM_RE.match(rest[-1]) or _NIL_RE.match(rest[-1])
        ):
            movement.append(rest.pop())
        movement.reverse()
        if len(movement) < _NCOLS or not rest:
            continue  # a division band title ("KLM COSMO") — no movement numbers

        # Peel a trailing packing token (bare count / N*M / N-M) if a real name precedes it.
        pack = ""
        if len(rest) >= 2 and _PACK_RE.match(rest[-1]):
            pack = rest.pop()
        product = " ".join(rest).strip()
        if not product:
            continue

        record = {
            "product_name": product,
            "opening_stock": _num_or_nil(movement[0]) or "0",
            "purchase_stock": _num_or_nil(movement[1]) or "0",
            "sales_qty": _num_or_nil(movement[2]) or "0",
            "closing_stock": _num_or_nil(movement[3]) or "0",
        }
        if pack:
            record["pack"] = pack
        if expiry:
            record["expiry"] = expiry
        records.append(record)

    detected = {
        "ITEM DESCRIPTION": "product_name",
        "OPENING": "opening_stock",
        "RECEIPT": "purchase_stock",
        "ISSUE": "sales_qty",
        "CLOSING": "closing_stock",
    }
    return records, detected
