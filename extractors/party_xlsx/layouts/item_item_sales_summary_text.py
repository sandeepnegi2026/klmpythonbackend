"""
"ITEM / ITEM WISE SALES SUMMARY" — single-column (fixed-width text) variant.

MARG ERP 9+ export (M/S BURIMAA MEDICAL AGENCY / KLM PHARMA). Same PRODUCT-banded semantics as
the columnar ``item_item_sales_summary``, but every row is ONE space-padded text cell (ncols == 1)
and the report carries an extra "AMOUNT ( % )" percentage-of-sales column:

    ITEM / ITEM WISE SALES SUMMARY FROM 01-05-2026-31-05-2026
    D E S C R I P T I O N            QTY.   FREE   RATE     AMOUNT ( % )   <- glued header (col0)
    BLEMGUARD FACE SERUM          30ML                                     <- product band
    BHOWMIK MEDICAL STORES-BADKUL      2      0   424.14    848.28   0.15  <- party line
    TOTAL :                            8      0            3425.39   0.60  <- per-item subtotal

Distinct from the columnar ``item_item_sales_summary`` (which reads [name|qty|free|rate|amount] as
real cells) — here the whole line is one glued cell, so the figures are parsed off the trailing
run of the text. Distinct from AGARTALA ``area_item_sales_summary`` (band is the PARTY there, the
PRODUCT here). ``marg_busy`` claims it on the shared "description"+"qty" header but extracts 0 rows
from the glued single column (RED UNKNOWN_LAYOUT), so this reader must sit ahead of it.

Gating is single-column: the header ``D E S C R I P T I O N ... AMOUNT`` lives entirely in col0
(``_header_idx`` matches col0 ALONE), whereas the columnar sibling spreads those words across real
cells so col0 there is just "D E S C R I P T I O N". The columnar sibling additionally carries no
"( % )" column, so the two never collide.

MAPPING: product_name / pack  <- product band (name + trailing pack split on the fixed-width gap);
party_name / party_location  <- customer cell (town peeled on the LAST '-' delimiter); qty /
free_qty ("-" -> 0) / rate / amount  <- the first four trailing numbers (the fifth, "( % )", is
discarded).
"""
import re

from extractors.party_xlsx.parse_common import cell_text, compact

_HEADER_COMPACT = "descriptionqtyfreerateamount"
_TITLE_COMPACT = "itemitemwisesalessummary"

# Product band glues "<name>  <pack>" (e.g. "BLEMGUARD FACE SERUM   30ML", "CETALORE TAB   10$")
# as one fixed-width column padded with a run of 2+ spaces; the LAST such run is the pack boundary.
_PACK_SPLIT_RE = re.compile(r"^(.*\S)\s{2,}(\S.*)$")
# A numeric figure token: 2, 0, 424.14, 1,286.25 (a lone "-" placeholder is handled separately).
_NUM_RE = re.compile(r"^-?\d[\d,]*\.?\d*$")

# Page-break furniture that repeats mid-report (the intro's vendor/address/gstin block is above the
# header row and skipped by starting after it; these are the shorter per-page repeats). Only tested
# on lines that are NOT party rows, so a real "M/S ..." customer — which always carries figures and
# is classified as a party first — is never dropped.
_FURNITURE_TOKENS = (
    "D E S C R I P T I O N", "ITEM / ITEM", "ITEM/ITEM", "CONTINUED", "PAGE NO",
    "END OF REPORT", "MARG ERP", "GSTIN", "E-MAIL", "REPORT FOR", "COMPANY",
)


def _norm(text):
    return str(text).replace("\xa0", " ")


def _header_idx(rows):
    # col0 ALONE must carry the whole compacted header — the single-column signature.
    for i, row in enumerate(rows[:30]):
        if row and _HEADER_COMPACT in compact(cell_text(row[0])):
            return i
    return None


def _is_dashes(text):
    s = text.strip()
    return bool(s) and set(s) <= set("-")


def _is_furniture(text):
    u = text.upper()
    return any(tok in u for tok in _FURNITURE_TOKENS)


def _trailing_numbers(line):
    """Split a glued line into (name_text, [figures]); figures is the trailing run of numeric
    tokens (a lone "-" counts as 0). Product bands return an empty figure list (the pack carries a
    unit letter/symbol), party lines return qty/free/rate/amount[/pct]."""
    toks = line.split()
    nums, i = [], len(toks) - 1
    while i >= 0 and (toks[i] == "-" or _NUM_RE.match(toks[i])):
        nums.insert(0, "0" if toks[i] == "-" else toks[i].replace(",", ""))
        i -= 1
    return " ".join(toks[: i + 1]), nums


def _split_party_town(name):
    """Peel a trailing town on the LAST '-' (the KLM/Marg "<PARTY>-<TOWN>" convention). The town is
    accepted only when short and non-numeric so a hyphen inside the trade name is never split."""
    if "-" in name:
        base, town = name.rsplit("-", 1)
        base, town = base.strip(), town.strip()
        if base and town and len(town) <= 25 and not any(ch.isdigit() for ch in town):
            return base, town
    return name, ""


def detect(rows):
    hidx = _header_idx(rows)
    if hidx is None:
        return False
    head = compact(" ".join(cell_text(row[0]) for row in rows[:15] if row))
    return _TITLE_COMPACT in head


def parse_item_item_sales_summary_text(rows):
    detected = {"D E S C R I P T I O N": "product_name", "QTY.": "qty",
                "FREE": "free_qty", "RATE": "rate", "AMOUNT": "amount"}
    hidx = _header_idx(rows)
    if hidx is None:
        return [], detected

    # Verbatim intro-block lines (vendor / address / phone / gstin / title / company) so a
    # page-break repeat that matches one exactly is skipped rather than read as a product band.
    header_block = {
        cell_text(r[0]).strip().upper()
        for r in rows[:hidx]
        if r and cell_text(r[0]).strip()
    }

    records, product, pack = [], "", ""
    for row in rows[hidx + 1:]:
        col0 = cell_text(row[0]).strip() if row else ""
        if not col0 or _is_dashes(col0):
            continue
        up0 = col0.upper()
        if up0.startswith("TOTAL") or up0.startswith("GRAND TOTAL"):
            continue

        line = _norm(col0).rstrip()
        name_text, nums = _trailing_numbers(line)

        # Party line: the four figure columns are present (qty, free, rate, amount[, %]).
        if len(nums) >= 4:
            if not product:
                continue
            qty, free, rate, amount = nums[0], nums[1], nums[2], nums[3]
            pname, ploc = _split_party_town(name_text)
            rec = {
                "party_name": pname,
                "product_name": product,
                "qty": qty,
                "free_qty": free,
                "rate": rate,
                "amount": amount,
            }
            if pack:
                rec["pack"] = pack
            if ploc:
                rec["party_location"] = ploc
            records.append(rec)
            continue

        # Otherwise a product band (starts a new item) — unless it is a page-break furniture line.
        if up0 in header_block or _is_furniture(line):
            continue
        m = _PACK_SPLIT_RE.match(line)
        if m:
            product, pack = m.group(1).strip(), m.group(2).strip()
        else:
            product, pack = line.strip(), ""

    return records, detected
