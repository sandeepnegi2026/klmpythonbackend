"""KLM/Marg "STOCK & SALES ANALYSIS" reduced OPENING/RECEIPT/ISSUE/CLOSING movement PDF.

AMETOMBI SALES AGENCIES (Marg ERP 9+) exports the KLM "STOCK & SALES ANALYSIS"
report as a flat text PDF (n_rects == 0). It is the PDF twin of the single-cell .xls
handled by the stock_xlsx `stock_sales_analysis_oic_xlsx` layout — the SAME report,
the SAME AMETOMBI books ship both a .PDF and a .XLS. The header, printed once per
page, is::

    ITEM DESCRIPTION                 OPENING   RECEIPT     ISSUE   CLOSING M.EXP

Unlike the 14-column full-movement sibling (`marg_stock_analysis_full`, which carries
S/R P/R SAMPLE) or the 11-column P.RETURN/S.RETURN/OTHERS sibling
(`klm_stock_sales_analysis_movement`), this reduced export carries ONLY four numeric
movement columns, so those parsers drop every row. The coarse `simple4` rule instead
STEALS these files but mis-maps them: on rows that carry a stray leading packing digit
(a bare "1"/"10" printed before OPENING) `simple4` binds the FIRST four numbers
(pack, opening, receipt, issue) and DROPS the real closing -> ~50% false SANITY_FAILED.

Each data line is::

    <product ... [pack]>   OPENING   RECEIPT   ISSUE   CLOSING   [M.EXP e.g. 3/27]

Map (verified: closing = opening + receipt - issue on 100% of product rows across both
AMETOMBI books, and identical to the xlsx sibling):

    OPENING  -> opening_stock
    RECEIPT  -> purchase_stock
    ISSUE    -> sales_qty        (NEVER derived from a value column; ISSUE is a qty col)
    CLOSING  -> closing_stock

'-' means nil (0). A stray packing token (a bare count like "1"/"10", an "N*M" strip like
"1*10", or an "N-M" band) can sit between the description and the four numbers; it is
peeled into `pack` so the name stays clean and the last-four movement window binds
correctly. The trailing "M.EXP" (nearest-expiry, `mm/yy`) is captured as `expiry`,
outside the sanity equation.

The report is division-banded (bare "KLM COSMO" / "KLM DERMA" / "KLM PEDIA" title lines)
with "TOTAL <4 value numbers>" subtotals and a trailing supplier ledger. Real products
also start with "KLM " (KLM C 20 SERUM, KLM-D3 60K CAP), so bands are NOT dropped by
prefix: the sole structural gate is "the line ends in four movement tokens with a valid
product description before them" -- band title lines carry no movement numbers and the
TOTAL/supplier lines are removed by _skip_line + a rupee-magnitude guard.
"""
import re

from extractors.stock_pdf.parse_common import _skip_line, _split_product_pack

# a movement token: an integer / decimal, or a bare '-' nil placeholder.
_NUM_RE = re.compile(r"^-?\d+(?:\.\d+)?$")
_NIL_RE = re.compile(r"^-+$")
_MEXP_RE = re.compile(r"^\d{1,2}/\d{2,4}$")
# a stray packing token wedged between the description and the movement numbers: a bare
# count ("1"/"10"), an "N*M" strip ("1*10"), or an "N-M" band ("1-10"). Unit-suffixed
# tokens ("60ML"/"30G") are genuine name descriptors and are left with the name.
_PACK_RE = re.compile(r"^\d+(?:[*\-x]\d+)?$")
_NCOLS = 4
# the movement columns are QUANTITIES; the report's only large numbers are the rupee
# VALUE totals printed on the TOTAL subtotal lines. A product's per-row movement value
# never approaches those, so a token >= this magnitude marks a value/subtotal line.
_VALUE_MAG = 100000.0


def _v(tok):
    return 0.0 if _NIL_RE.match(tok) else float(tok.replace(",", ""))


def parse_stock_item_desc_oric_movement(text):
    records = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or set(line) <= set("-= "):
            continue
        if _skip_line(line):
            continue

        toks = line.split()
        # peel a trailing M.EXP (nearest-expiry) token, then the last four movement cols.
        expiry = toks.pop() if toks and _MEXP_RE.match(toks[-1]) else ""

        movement = []
        rest = toks[:]
        while rest and len(movement) < _NCOLS and (
            _NUM_RE.match(rest[-1]) or _NIL_RE.match(rest[-1])
        ):
            movement.append(rest.pop())
        movement.reverse()
        # a division band ("KLM COSMO") or non-data line: no 4-number movement tail,
        # or nothing but numbers left (the "TOTAL <values>" / supplier rows).
        if len(movement) < _NCOLS or not rest:
            continue
        if not re.search(r"[A-Za-z]", " ".join(rest)):
            continue

        vals = [_v(t) for t in movement]
        # rupee-magnitude guard: a per-row product movement is a unit count, never the
        # lakh-scale VALUE printed on TOTAL lines (which _skip_line already drops, but
        # keep this as a belt-and-braces guard against a stray value row).
        if any(abs(v) >= _VALUE_MAG for v in vals):
            continue

        # peel a stray packing token (bare count / N*M / N-M) if a real name precedes it.
        pack = ""
        if len(rest) >= 2 and _PACK_RE.match(rest[-1]):
            pack = rest.pop()
        name = " ".join(rest).strip()
        if not name or len(name) < 2:
            continue
        base_name, extracted_pack = _split_product_pack(name)
        base_name = re.sub(r"\s+", " ", base_name).strip()
        if not base_name:
            continue

        rec = {
            "product_name": base_name,
            "opening_stock": vals[0],
            "purchase_stock": vals[1],
            "sales_qty": vals[2],
            "closing_stock": vals[3],
        }
        # Prefer a real unit pack ("50GM"/"1*10") peeled off the name over the stray
        # leading count column ("1"), which is only a fallback when no unit pack exists.
        if extracted_pack:
            rec["pack"] = extracted_pack
        elif pack:
            rec["pack"] = pack
        if expiry:
            rec["expiry"] = expiry
        records.append(rec)
    return records
