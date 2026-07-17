import re

# ---------------------------------------------------------------------------
# METRO MEDICAL AGENCIES (Nagpur) "Party Sale Report" — banded party layout.
#
# One vendor, one KLM division per file ("Company: KLM <DIVISION>"), a
# "D/M/YYYY to D/M/YYYY" period line, then a single flat column of rows in which
# BOTH the party heading AND its item lines end in numbers.  There is no bill /
# date / batch column: a party is a running-total header followed by its product
# lines, e.g.
#
#     A TO Z MEDICAL & GEN. STORES DHANTOLI   5   0   662.87   <- PARTY (qty_T, amt_T)
#     ZYDIP-C LOTION 50ML                     1   0   171.43   <- item
#     ZYDIP-C LOTION 30ML                     4   0   491.44   <- item  (sums close band)
#
# TWO dialects share this parser, distinguished only by the column header:
#   * 3-num "Particulars Address/unit Qty Scm Qty Amount": every row carries an
#     Address/unit slot between the name and the numbers.  For a PARTY row that
#     slot is an alphabetic AREA word ("DHANTOLI", "RAJAPETH"); for an ITEM row
#     it is a pack token ("30ML", "20GM", "TAB 10'S").  Rows are
#         <text> [- ] <Qty:int> <Scm Qty:int> <Amount:money>
#     (party rows often print a bare "- " before the numbers).  Free scheme qty
#     -> free_qty.
#   * 2-num "Particulars Qty Amount": no Address/unit column, rows are
#         <text> <Qty:int> <Amount:money>   (no free_qty column).
#
# Band detection (spec):
#   The FIRST numeric row after a header is the PARTY header, capturing its
#   running totals (qty_T, amt_T).  Following numeric rows are accumulated as
#   ITEMS; when the running item sums equal (qty_T, amt_T) the band closes and
#   the next numeric row is the next PARTY header.  If the sums would OVERSHOOT
#   amt_T before reaching equality (a page-split band whose header total was
#   never matched, or a rounding gap), we fall back to a per-row UNIT-COLUMN
#   heuristic: a pack-like Address/unit slot marks an ITEM, an alphabetic AREA
#   word marks a PARTY (3-num only; the 2-num dialect has no unit column and
#   relies solely on the sum rule).
#
# Non-numeric interior lines are ADDRESS CONTINUATIONS ("248 SHOPNO",
# "O1GRFLHOUSE") reprinted below the party heading — skipped.  The footer
# "Totals <grand>" and the page furniture (vendor banner, title, "Company:",
# the period line, "Page No.", "Continued...", the repeated column header) are
# skipped too.  Grand "Totals" is used for triage only, not emitted.
#
# Field map: party text -> party_name (3-num dialect may peel a trailing AREA
# word into party_location, guarded by a _BIZ-suffix check like
# manufacturerwise_billwise; else the whole string is kept); item text ->
# product_name (pack tail left in the name); Qty -> qty; Scm Qty -> free_qty;
# Amount -> amount.  NO rate column exists and qty is NEVER derived from a value.
# ---------------------------------------------------------------------------

# Business/role words that must never be peeled off as an area (guards the peel).
_BIZ = {
    "MEDICAL", "MEDICALS", "MEDICOS", "MEDICOSE", "MEDICOSE.", "MEDICINE",
    "PHARMA", "PHARMACY", "STORE", "STORES", "STORES.", "AGENCIES", "AGENCY",
    "CHEMIST", "CHEMISTS", "SURGICAL", "SURGICALS", "GENERAL", "GENERALS",
    "DISTRIBUTORS", "TRADERS", "ENTERPRISES", "CARE", "MART", "AND", "CO",
    "CORPORATION", "GEN", "GEN.", "STROES", "CENTRE", "CENTER", "POINT",
    "SUPPLIES", "HEALTHCARE",
}

# Header of the 3-num dialect. "Scm Qty" (with its Address/unit slot) is present
# ONLY in the 3-number export; the 2-num export header is "Particulars Qty Amount".
_HDR_3NUM = re.compile(r"scm\s*qty", re.I)

# 3-num row: <text> [- ] <Qty> <Scm Qty> <Amount>.  The optional bare "- " that
# party rows print just before the numbers is consumed and discarded.
_ROW_3 = re.compile(
    r"^(.*?)\s+(?:-\s+)?(\d+)\s+(\d+)\s+([\d,]+\.\d{2})$"
)
# 2-num row: <text> <Qty> <Amount>.
_ROW_2 = re.compile(
    r"^(.*?)\s+(\d+)\s+([\d,]+\.\d{2})$"
)

# A pack-like Address/unit slot on an ITEM row ("30ML", "20GM", "TAB 10'S",
# "10", "10'S", "5ML"). Party rows carry an alphabetic AREA word instead.
_PACK_UNIT = re.compile(r"\d+\s*(ML|GM|GMS|G|TAB|CAP|'S|S)\b", re.I)


def _is_structural(low):
    """Page furniture / header / footer lines to skip outright."""
    if not low:
        return True
    if low.startswith("totals"):
        return True
    if low.startswith("particulars"):
        return True
    if low.startswith("company:"):
        return True
    if low.startswith("page no"):
        return True
    if low.startswith("continued"):
        return True
    if "party sale report" in low:
        return True
    if "metro medical agencies" in low:
        return True
    # "D/M/YYYY to D/M/YYYY" period line.
    if re.match(r"^\d{1,2}/\d{1,2}/\d{4}\s+to\s+\d{1,2}/\d{1,2}/\d{4}$", low):
        return True
    return False


def _split_area(name):
    """3-num party rows print "<PARTY NAME> <AREA>"; the AREA is the trailing
    token(s) after the business name (e.g. "A TO Z MEDICAL & GEN. STORES
    DHANTOLI" -> name "A TO Z MEDICAL & GEN. STORES", area "DHANTOLI").  Peel the
    LAST token as the area, guarded so a business/role word ("STORES", "PHARMA")
    or a numeric/too-short token is never stolen (mirrors
    manufacturerwise_billwise._split_town's _BIZ guard).  A pincode/comma tail is
    trimmed off the peeled area."""
    raw = name.strip().rstrip(" ,.-").strip()
    parts = raw.rsplit(None, 1)
    if len(parts) < 2:
        return raw, ""
    head, last = parts[0], parts[1]
    area = re.sub(r"-?\d+$", "", last.strip().strip(".,").strip()).strip()
    if (
        not re.fullmatch(r"[A-Za-z][A-Za-z.]*", area)
        or area.upper() in _BIZ
        or len(area) < 3
    ):
        return raw, ""
    return head.strip().rstrip(" ,.-").strip() or raw, area


def _to_amt(tok):
    return tok.replace(",", "")


def parse_party_sale_report(text):
    lines = text.splitlines()

    # Dialect: 3-num when the column header carries "Scm Qty", else 2-num.
    three = False
    for ln in lines:
        s = ln.strip()
        if s.lower().startswith("particulars"):
            three = bool(_HDR_3NUM.search(s))
            break

    # "Free" is the canonical free_qty synonym (the file prints the column as
    # "Scm Qty", which is NOT a header synonym; label it "Free" so it maps).
    if three:
        headers = ["Party Name", "Area", "Product Name", "Qty", "Free", "Amount"]
    else:
        headers = ["Party Name", "Product Name", "Qty", "Amount"]

    rows = []
    party = ""            # current party_name
    party_area = ""       # current party_location (3-num only)
    open_band = False     # a party band is currently accumulating items
    run_qty = 0           # running sum of item qty within the band
    run_amt = 0           # running sum of item amount (in paise) within the band
    tgt_qty = 0
    tgt_amt = 0

    for raw in lines:
        s = raw.strip()
        low = s.lower()
        if _is_structural(low):
            continue

        m = _ROW_3.match(s) if three else _ROW_2.match(s)
        if not m:
            # Non-numeric interior line = address continuation -> skip.
            continue

        if three:
            text_part, qty, scm, amt = m.groups()
        else:
            text_part, qty, amt = m.groups()
            scm = "0"
        text_part = text_part.strip()
        qty_i = int(qty)
        amt_p = int(round(float(_to_amt(amt)) * 100))

        # Decide PARTY vs ITEM.
        is_party = False
        if not open_band:
            # First numeric row after a header always starts a new party band.
            is_party = True
        else:
            nxt_qty = run_qty + qty_i
            nxt_amt = run_amt + amt_p
            if nxt_qty == tgt_qty and nxt_amt == tgt_amt:
                # This item closes the band exactly -> it is the LAST item.
                is_party = False
            elif nxt_amt > tgt_amt or nxt_qty > tgt_qty:
                # Would overshoot the party total -> the band's header total was
                # never matched (page-split / rounding). Fall back to the unit
                # heuristic to classify this row.
                if three:
                    is_party = not _looks_like_item(text_part, s)
                else:
                    # 2-num has no unit column: an overshoot means the previous
                    # band ended (its total was already met or is unreachable),
                    # so treat this row as the next party header.
                    is_party = True
            else:
                is_party = False

        if is_party:
            if three:
                pname, parea = _split_area(text_part)
                party, party_area = pname, parea
            else:
                party, party_area = text_part, ""
            tgt_qty = qty_i
            tgt_amt = amt_p
            run_qty = 0
            run_amt = 0
            open_band = True
            continue

        # ITEM row.
        if three:
            rows.append([party, party_area, text_part, qty, scm, _to_amt(amt)])
        else:
            rows.append([party, text_part, qty, _to_amt(amt)])
        run_qty += qty_i
        run_amt += amt_p
        if run_qty == tgt_qty and run_amt == tgt_amt:
            # Band closed exactly; next numeric row opens a new party.
            open_band = False

    return headers, rows


def _looks_like_item(text_part, full_line):
    """Unit-column fallback: the Address/unit slot of an ITEM row is pack-like
    ("30ML", "TAB 10'S"), while a PARTY row's slot is an alphabetic AREA word.
    The Address/unit slot is the run BETWEEN the trailing "text" and the numbers;
    since the whole product/pack is captured in ``text_part`` for items, testing
    the captured text's tail for a pack token is a reliable item signal."""
    return bool(_PACK_UNIT.search(text_part))
