"""
"ITEM / ITEM WISE SALES SUMMARY" — MARG ERP 9+ product-wise sales export
(SRI SRINIVASA MEDICAL AGENCIES / KLM PHARMA). One band per PRODUCT (item), then the
customers (parties) who bought it, then a per-item ``TOTAL :`` line:

    ITEM / ITEM WISE SALES SUMMARY FROM 01-05-2026-31-05-2026
    D E S C R I P T I O N            QTY.   FREE   RATE     AMOUNT     <- header row
    EBERFINE CREAM                30GM                                 <- product band (col0)
    HANUMAN MEDICAL & GEN STORE-S   10     1      220.14   2201.38     <- party line (columnar)
    TOTAL :                         10     1               2201.38     <- per-item subtotal -> skip

Distinct from the AGARTALA ``area_item_sales_summary`` (title "AREA / ITEM ...") two ways:
(1) the band is the PRODUCT here, not the party (the semantics are inverted); and
(2) the party lines are proper COLUMNAR cells [name, qty, free, rate, amount], not a single
space-padded text cell. So this needs its own reader — the AREA layout's fixed-width text
regexes do not apply, and ``marg_busy`` (which currently claims it on the shared
"description"+"qty" header) reads the product band as the party and the customer as the product.

MAPPING: product_name / pack  <- product band (name + trailing pack split on the fixed-width
gap); party_name / party_location <- customer cell (town peeled only on a multi-space gap);
qty / free_qty ("-" -> 0) / rate / amount <- the four numeric columns.
"""
import re

from extractors.party_xlsx.parse_common import cell_text, compact

# The product band glues "<name>  <pack>" (e.g. "EBERFINE CREAM   30GM", "KLCLAV-625 TAB  10S")
# and a party cell may glue "<name>  <town>" ("SRI THAKUR MEDICAL   BANGALI"). Both are a single
# fixed-width column padded with a run of 2+ spaces, so the LAST such run is the column boundary.
# The greedy first group binds the split to that last 2+ space run; single spaces inside a name
# ("EBERFINE XL 50GM TUBE", "SRI THAKUR MEDICAL") are never touched.
_TRAIL_RE = re.compile(r"^(.*\S)\s{2,}(\S.*)$")

# Footer / page-furniture that can appear as an all-identical merged row after the header and
# must never be read as a product band (the header-block lines above the header row are handled
# separately by matching them verbatim).
_FURNITURE_TOKENS = (
    "MARG ERP", "IMPORT PURCHASE", "D E S C R I P T I O N", "ITEM / ITEM", "ITEM/ITEM",
    "GRAND TOTAL", "PAGE NO", "CONTINUED", "GSTIN", "REPORT FOR",
)

# Under each product band, every real customer line is followed by its invoice/credit-note
# DETAIL line — an invoice/challan/CN code in col0 ("AM2627-0262813-06 EB503", "CN00167 26-06
# AG3607", "AMCH-05920 26-06 CX527") that DUPLICATES the customer's qty/amount (the customer line
# already carries the correct net rate/amount and is what the per-item TOTAL reconciles to).
# Emitting the detail line as a second "party" double-counts the sale, so it is skipped. Two
# signature a real customer name never has: a 2-4 letter code prefix glued straight to 3+ digits
# ("AM2627...", "CN00167") or to a dash+2digits ("AMCH-05920"). Requiring 3+ glued digits keeps a
# short real name like "ABC12 MEDICAL" safe. Files without such detail lines never match and are
# byte-for-byte unaffected.
_DOCNO_RE = re.compile(r"^[A-Z]{2,4}(?:\d{3,}|-\d{2,})")


def _split_trailing(text):
    """Peel a trailing fixed-width column: return (head, tail); tail is "" when there is no
    2+ space gap. Used for product->(name, pack) and party->(name, town)."""
    text = str(text).replace("\xa0", " ").rstrip()
    m = _TRAIL_RE.match(text)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return text.strip(), ""


def _is_furniture(text):
    u = str(text).upper()
    return any(tok in u for tok in _FURNITURE_TOKENS)


def _header_idx(rows):
    for i, row in enumerate(rows[:30]):
        if "descriptionqtyfreerateamount" in compact(" ".join(cell_text(c) for c in row)):
            return i
    return None


def _is_columnar_header(rows):
    """True when the DESCRIPTION..AMOUNT header is spread across SEPARATE real cells
    (the columnar signature), rather than glued into a single space-padded text cell.

    This is the invariant that tells this columnar reader from its single-column TEXT
    sibling (``item_item_sales_summary_text``): here QTY./FREE/RATE/AMOUNT each sit in
    their own cell, so ``compact(col0)`` alone is just "description"; in the TEXT export
    the whole header lives in col0 (``compact(col0)`` already carries the numeric labels).
    Used so a ``( % )`` percentage column can be accepted for the COLUMNAR family (KASERA
    DRUG "KLM ALL DIVISON PARTY WISE") without letting the TEXT variant leak in.
    """
    idx = _header_idx(rows)
    if idx is None:
        return False
    row = rows[idx]
    if not row or "descriptionqtyfreerateamount" in compact(cell_text(row[0])):
        # col0 alone already holds the full header run -> single glued cell (TEXT variant).
        return False
    labelled = sum(
        1
        for c in row
        if compact(cell_text(c)) in ("qty", "free", "rate", "amount")
    )
    return labelled >= 3


def detect(rows):
    head = compact(" ".join(" ".join(cell_text(c) for c in r) for r in rows[:15]))
    # Title token — "ITEM / ITEM WISE SALES SUMMARY" compacts to this. It does NOT contain the
    # AGARTALA "areaitemwisesalessummary" nor the "partyitemwisesalessummary" token, so the two
    # sibling summary layouts stay on their own readers.
    if "itemitemwisesalessummary" not in head:
        return False
    if "descriptionqtyfreerateamount" not in head:
        return False
    # Paren-guard, mirroring the AREA/percent-column variant: the four-numeric-column report
    # carries no "( % )" discount column. EXCEPTION (additive, gated): a genuinely COLUMNAR
    # export (KASERA DRUG "KLM ALL DIVISON PARTY WISE") may print a trailing "( % )" column and
    # is still this layout — its header sits in separate real cells (``_is_columnar_header``),
    # which the single-column TEXT sibling (that the "%" guard was meant to protect) never does.
    # So the "%" rejection applies ONLY when the header is NOT columnar, leaving the TEXT variant
    # and every existing "%"-free file untouched.
    raw_head = " ".join(" ".join(cell_text(c) for c in r) for r in rows[:15])
    if "%" in raw_head and not _is_columnar_header(rows):
        return False
    return True


def parse_item_item_sales_summary(rows):
    detected = {"D E S C R I P T I O N": "product_name", "QTY.": "qty",
                "FREE": "free_qty", "RATE": "rate", "AMOUNT": "amount"}
    hidx = _header_idx(rows)
    if hidx is None:
        return [], detected

    # Verbatim header-block lines (vendor name / address / phone / GSTIN / title / company) so a
    # page-break repeat of that block mid-report is skipped rather than read as a product band.
    header_block = {
        cell_text(r[0]).strip().upper()
        for r in rows[:hidx]
        if r and cell_text(r[0]).strip()
    }

    records, product, pack = [], "", ""
    for row in rows[hidx + 1:]:
        cells = [cell_text(c) for c in row]
        col0 = cells[0].strip() if cells else ""
        if not col0:
            continue
        up0 = col0.upper()
        if up0.startswith("TOTAL") or up0.startswith("GRAND TOTAL"):
            continue
        tail = [cells[i].strip() if i < len(cells) else "" for i in (1, 2, 3, 4)]
        populated = [c for c in cells if c.strip()]
        # A product band is either a lone col0 cell (cols 1-4 empty) or an all-identical merged
        # row; a party line has the customer in col0 and the four numeric columns filled.
        is_single = not any(tail)
        is_merged = len(set(populated)) == 1 and len(populated) >= 2
        if is_single or is_merged:
            if up0 in header_block or _is_furniture(col0):
                continue
            product, pack = _split_trailing(col0)
            continue
        # party line
        if not product:
            continue
        # Skip a page-break repeat of the title/header block and the invoice/credit-note DETAIL
        # line that duplicates the customer's sale (see _DOCNO_RE) — both otherwise leak in as a
        # bogus/duplicate party. Real customer lines never match either, so this is additive.
        if up0 in header_block or _is_furniture(col0) or _DOCNO_RE.match(col0):
            continue
        qty, free, rate, amount = tail
        pname, ploc = _split_trailing(col0)
        # Only accept a peeled town: reject a numeric/over-long tail so a genuine part of the
        # customer name is never shaved off (party cells never carry trailing digits — the
        # figures live in their own columns).
        if not ploc or any(ch.isdigit() for ch in ploc) or len(ploc) > 20:
            pname, ploc = col0, ""
        free = "0" if free in ("-", "") else free.replace(",", "")
        rec = {
            "party_name": pname,
            "product_name": product,
            "qty": qty.replace(",", ""),
            "free_qty": free,
            "rate": rate.replace(",", ""),
            "amount": amount.replace(",", ""),
        }
        if pack:
            rec["pack"] = pack
        if ploc:
            rec["party_location"] = ploc
        records.append(rec)

    return records, detected
