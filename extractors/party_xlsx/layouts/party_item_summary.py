"""
"PARTY / ITEM WISE SALES SUMMARY" — a Busy/Tally text export (PRASAD, GLOBE, KUSHAL,
RAJA) where the whole report is space-padded text, typically crammed into a single
column (or, when the sheet merges cells, repeated across every column):

    PARTY / ITEM WISE SALES SUMMARY FROM 01-05-2026-31-05-2026
    D E S C R I P T I O N            QTY.    FREE    RATE    AMOUNT  ( % )
    AGARWAL MEDICAL STORE(PALIYA)                                          <- party band (name only)
    KLM D3 NANO SHOTS  5ML            5       2      55.65    278.25   0.25 <- product line
    TOTAL :                          15       6              1243.42   1.10 <- per-party total

The party heads a band that is a bare name row (no trailing numbers); each product
line is the description followed by the QTY / [FREE] / RATE / AMOUNT / (%) figures.
Because the columns are positional text, the values are read as the trailing numeric
tokens of the line (mapped right-to-left against the header's numeric columns). The
generic readers cannot attach the party here because it is a band, not a column, and
the figures live inside one text cell.
"""
import re

from core.header_match import normalize

from extractors.party_xlsx.parse_common import cell_text

_TITLE = "party item wise sales summary"
_NUM_RE = re.compile(r"^-?[\d,]+\.?\d*$")
_DASHES_RE = re.compile(r"^[-=\s]+$")

# --- "<name>-<area>[-L.]" party convention (MARG Jodhpur "Local" exports, e.g. SIDDHI
# VINAYAK): each party band carries its town as a trailing "-<AREA>" segment, often
# followed by a "-L"/"-L." Local marker. Everything below is GATED on the file actually
# using this convention (``_uses_local_convention``); other party_item_summary vendors,
# whose bands have no such suffix, take the ``use_conv == False`` path and stay
# byte-identical to before (no party_location, no band skipping).
_LOCAL_MARKER_RE = re.compile(r"[-–]\s*L\.?\s*$", re.IGNORECASE)


def _split_location(name):
    """Peel a trailing '-L'/'-L.' Local marker and the '-<area>' segment off a band.

    Returns (party_name, party_location); party_location is "" when nothing splits.
    """
    s = name.strip()
    m = _LOCAL_MARKER_RE.search(s)
    core = s[: m.start()].rstrip() if m else s
    if "-" in core:
        head, _, tail = core.rpartition("-")
        head, tail = head.strip(), tail.strip()
        if head and re.search(r"[A-Za-z]", tail) and len(tail) <= 25:
            return head, tail
    return (core.strip() if m else s), ""


def _split_area(name):
    """Split a "FIRM NAME-<area>" band into (party_name, party_location). Unlike
    ``_split_location`` there is no "-L" Local marker: the town is simply the segment
    after the LAST hyphen. A trailing bare "-" (area omitted, e.g. "AB MEDI OZAR-") is
    stripped to a clean name with empty location.
    """
    s = name.strip()
    if "-" in s:
        head, _, tail = s.rpartition("-")
        head, tail = head.strip(), tail.strip()
        if head and re.search(r"[A-Za-z]", tail) and len(tail) <= 25:
            return head, tail
        if head and not tail:
            return head, ""
    return s, ""


def _is_page_noise(text, vendor_c):
    """A repeated page header/title/footer that leaks in as a fake party band."""
    n = normalize(text)
    c = n.replace(" ", "")
    if "description" in c and "qty" in c:        # repeated column header
        return True
    if "partyitemwisesalessummary" in c:          # repeated report title
        return True
    if "endofreport" in c:
        return True
    if c.startswith("continued"):                 # "Continued..2" page footer
        return True
    if n.startswith("grand total"):
        return True
    if vendor_c and len(vendor_c) >= 6 and c.startswith(vendor_c):  # repeated vendor name
        return True
    return False


def _uses_local_convention(rows, header_idx):
    """True once >=8 party bands carry the '-L'/'-L.' Local marker — the signal that
    the trailing '-<area>' is a town (party_location), not part of the firm name."""
    marked = 0
    for raw in rows[header_idx + 1:]:
        distinct = [c for c in (cell_text(x) for x in raw) if c]
        if not distinct or len(set(distinct)) != 1:
            continue
        text = _ws(distinct[0])
        toks = text.split()
        while toks and _is_num(toks[-1]):
            toks.pop()
        if toks and _LOCAL_MARKER_RE.search(text):   # a bare name band ending in -L
            marked += 1
            if marked >= 8:
                return True
    return False


def _uses_area_convention(rows, header_idx, vendor_c):
    """True when most party bands carry a plain trailing "-<area>" town suffix but NO
    "-L"/"-L." Local marker — the signal that the last hyphen splits firm from town
    (e.g. UNIQUE PHARMA's Nashik export: "ANVI PHARMA-NASHIK ROAD", "ASHOKA CHEMIST-
    ASHOKA MARG"). Gated on a high band hit-rate (>=8 bands AND >=50% of real bands) so a
    vendor whose firm names merely happen to contain a stray hyphen (SHREE HARISH ~16%,
    PRATAP 0%) is untouched and keeps its whole band as party_name."""
    total = suffix = 0
    for raw in rows[header_idx + 1:]:
        distinct = [c for c in (cell_text(x) for x in raw) if c]
        if not distinct or len(set(distinct)) != 1:
            continue
        text = _ws(distinct[0])
        toks = text.split()
        while toks and _is_num(toks[-1]):
            toks.pop()
        if not toks:                                  # product line (all-numeric tail)
            continue
        if _is_total_label(text) or _is_page_noise(text, vendor_c):
            continue
        total += 1
        _head, tail = _split_area(text)
        if tail or text.rstrip().endswith("-"):
            suffix += 1
    return suffix >= 8 and suffix >= 0.5 * total


# Business-type trailing words that are NEVER a town — keeps the space-glued-town split
# below from peeling a firm-type suffix (STORE, MEDICALS, PHARMA…) as if it were a place.
_BIZ_TAIL = {
    "store", "stores", "store.", "medical", "medicals", "medico", "medicos", "medicoz",
    "medicose", "pharma", "pharmacy", "pharmecy", "agency", "agencies", "surgical",
    "surgicals", "centre", "center", "co", "co.", "sons", "company", "enterprise",
    "enterprises", "distributors", "distributor", "traders", "drug", "drugs", "chemist",
    "chemists", "hall", "medicine", "medicines", "dawakana", "sales", "corner", "point",
}


def _glued_towns(rows, header_idx, vendor_c):
    """Detect a town this vendor SPACE-GLUES onto party bands with no delimiter
    (S.R.MEDICALS: "ADARSH MEDICAL STORE BASTI", "MALHOTRA MEDICALS BASTI" — town = BASTI).

    Returns the set of trailing words that recur as a town across the file: a word qualifies
    only when it is the LAST word of >=8 bands AND >=25% of real bands AND is not a business-
    type word. Empty for vendors without this pattern, so those files stay byte-identical.
    Only consulted when neither hyphen convention (-L / -<area>) applies."""
    tails = {}
    total = 0
    for raw in rows[header_idx + 1:]:
        distinct = [c for c in (cell_text(x) for x in raw) if c]
        if not distinct or len(set(distinct)) != 1:
            continue
        text = _ws(distinct[0])
        toks = text.split()
        while toks and _is_num(toks[-1]):
            toks.pop()
        if len(toks) < 2:                                   # need name + a trailing word
            continue
        if _is_total_label(text) or _is_page_noise(text, vendor_c):
            continue
        total += 1
        last = toks[-1].strip(".,").lower()
        if last and last not in _BIZ_TAIL and not _is_num(last):
            tails[last] = tails.get(last, 0) + 1
    if not total:
        return set()
    return {word for word, count in tails.items() if count >= 8 and count >= 0.25 * total}


def _split_glued_town(name, towns):
    """Peel a trailing space-glued town word (from ``_glued_towns``) into party_location."""
    toks = name.split()
    if len(toks) >= 2 and toks[-1].strip(".,").lower() in towns:
        return " ".join(toks[:-1]).strip(), toks[-1].strip(".,")
    return name, ""


def _ws(text):
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def _is_total_label(text):
    """A per-party / grand-total footer row (never a product). ``startswith('total')``
    alone misses "GRAND TOTAL :" — which, when it carries figures in separate columns,
    was emitted as a bogus product and double-counted the amount."""
    t = text.strip().lower()
    return t.startswith("total") or t.startswith("grand total")


def _is_num(tok):
    return bool(tok) and bool(_NUM_RE.match(tok.replace(",", "")))


def _num_val(cell):
    match = re.search(r"-?[\d,]+\.?\d*", cell)
    return match.group(0).replace(",", "") if match else ""


def _to_float(v):
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _derive_qty(record):
    """Recover QTY when a MARG export leaves the QTY cell blank on a straight sale.

    Some rows print the RATE and AMOUNT but leave QTY empty (rendered as a blank
    cell, e.g. DERMA "MFSONE CREAM 30GM" rate 159.35 amount 318.70 = qty 2); the
    per-party and GRAND TOTAL still count that qty, so leaving it 0 under-counts the
    quantity total. Derive qty = round(amount / rate) ONLY when: qty is missing/0,
    both rate and amount are non-zero, and the rounded quotient exactly reproduces
    the amount (round(qty)*rate == amount within a cent). Any row with a real qty, a
    zero-value line, or a non-integer quotient is left untouched, so files without a
    blanked-qty line stay byte-identical.
    """
    qty = _to_float(record.get("qty"))
    if qty not in (None, 0.0):
        return
    rate = _to_float(record.get("rate"))
    amount = _to_float(record.get("amount"))
    if not rate or amount in (None, 0.0):
        return
    q = round(amount / rate)
    if q and abs(q * rate - amount) <= 0.01 * max(1.0, abs(amount)):
        record["qty"] = str(q)


def title_matches(rows):
    head = normalize(" ".join(" ".join(cell_text(c) for c in r) for r in rows[:8]))
    return _TITLE in head


def _find_header(rows):
    for idx, row in enumerate(rows[:15]):
        # the header spaces out the letters ("D E S C R I P T I O N"), so compare on the
        # de-spaced form
        compact = normalize(" ".join(cell_text(c) for c in row)).replace(" ", "")
        if "description" in compact and "qty" in compact and ("amount" in compact or "rate" in compact):
            return idx
    return None


def _qty_col_is_nonnumeric(rows, header_idx):
    """True when the QTY column carries pack units ("2 Pcs"), not bare numbers.

    This is exactly the case ``marg_busy`` cannot handle: its ``is_numeric_qty`` gate
    parses "2 Pcs" as NaN, so it treats every product line as a band and extracts 0
    rows (the file then mis-falls through to the generic ``tabular`` reader, which has
    no party column). Bare-number qty columns stay with ``marg_busy``.
    """
    header = [cell_text(c) for c in rows[header_idx]]
    qty_col = next((i for i, c in enumerate(header) if "qty" in normalize(c)), 1)
    numeric = unit = 0
    for raw in rows[header_idx + 1: header_idx + 200]:
        cells = [cell_text(c) for c in raw]
        nonempty = [c for c in cells if c]
        # skip merged band rows and blank/short rows — only weigh real product lines
        if len(nonempty) <= 1 or len(set(nonempty)) == 1 or qty_col >= len(cells):
            continue
        val = cells[qty_col]
        if not val or val.lower().startswith("total"):
            continue
        if _NUM_RE.match(val.replace(",", "")):
            numeric += 1
        else:
            unit += 1
    return unit >= 2 and unit > numeric


def detect(rows):
    if not title_matches(rows):
        return False
    header_idx = _find_header(rows)
    if header_idx is None:
        return False
    single = multi = 0
    for raw in rows[header_idx + 1: header_idx + 60]:
        nonempty = [c for c in (cell_text(x) for x in raw) if c]
        if not nonempty:
            continue
        if len(nonempty) == 1 or len(set(nonempty)) == 1:
            single += 1
        else:
            multi += 1
    # Single-column text variant: the whole line is packed into one cell (or merged
    # across cells so every cell is identical). ``marg_busy`` cannot read the figures
    # out of the text, so we own it — require single-column rows to dominate.
    if single >= 3 and single > multi:
        return True
    # Multi-column merged-band variant (KUSHAL): genuine QTY/RATE/AMOUNT columns but the
    # party is a merged full-width band and the QTY carries a pack unit ("2 Pcs"). Only
    # claim it when ``marg_busy`` would fail (qty column non-numeric); bare-number qty
    # files keep flowing to ``marg_busy`` untouched, so working files cannot regress.
    if single >= 2 and multi >= 2 and _qty_col_is_nonnumeric(rows, header_idx):
        return True
    # Any file under the "PARTY / ITEM WISE SALES SUMMARY" title (required above) with the
    # spaced DESCRIPTION/QTY/FREE/RATE/AMOUNT header that has BOTH party band rows (single-
    # cell or merged full-width names) and multi-column product rows is this format. Whether
    # the bands are single-cell (PRATAP COSMOQ/DERMA/...) or merged (PRATAP COSMOCOR),
    # party_item_summary reads them correctly, while marg_busy mis-reads the free="-" rows as
    # new party bands (party_name <- a product like "RESOTEN") and drops parties. The title
    # gate keeps this from touching any non-summary layout.
    if single >= 2 and multi >= 2:
        return True
    return False


def parse_party_item_summary(rows):
    header_idx = _find_header(rows)
    if header_idx is None:
        return [], {}
    hjoined = normalize(" ".join(cell_text(c) for c in rows[header_idx]))
    # ``normalize`` strips "%", so read the trailing percentage column off the raw header
    # instead. Some MARG exports (SHREE BALAJI) omit "( % )" entirely; assuming it is
    # always present shifts the right-aligned values one slot and drops qty.
    has_pct = any("%" in cell_text(c) for c in rows[header_idx])
    # numeric columns present, in left-to-right order (the trailing "( % )" is dropped)
    cols = ["qty"]
    if "free" in hjoined:
        cols.append("free_qty")   # canonical field (was "free", which never reached free_qty)
    cols += ["rate", "amount"]
    if has_pct:
        cols.append("pct")
    ncol = len(cols)

    def _emit(product, vals, current_party, current_loc):
        # align the trailing values to the rightmost columns
        keep = vals[-ncol:]
        record = {"party_name": current_party, "product_name": product}
        if current_loc:
            record["party_location"] = current_loc
        for key, val in zip(cols[-len(keep):], keep):
            if key != "pct":
                record[key] = val
        _derive_qty(record)
        return record

    # ``use_conv`` gates the "<name>-<area>[-L.]" Local handling. When False (every other
    # party_item_summary vendor) the band branches below are identical to before: the whole
    # band becomes party_name, no party_location, no page-noise skipping.
    vendor_c = normalize(cell_text(rows[0][0]) if rows and rows[0] else "").replace(" ", "")
    use_conv = _uses_local_convention(rows, header_idx)
    # A separate, mutually-exclusive convention: bands carry a plain "-<area>" town suffix
    # with NO "-L" marker (UNIQUE PHARMA Nashik export). Only consulted when the "-L" path
    # is off, and itself gated on a high band hit-rate so other vendors stay untouched.
    use_area = not use_conv and _uses_area_convention(rows, header_idx, vendor_c)
    # A third, mutually-exclusive convention: the town is SPACE-glued onto the band with no
    # delimiter (S.R.MEDICALS Basti: "ADARSH MEDICAL STORE BASTI"). Only consulted when neither
    # hyphen convention applies, and returns towns only when a non-business word recurs as the
    # trailing word of >=8 and >=25% of bands — so other vendors get an empty set and stay
    # byte-identical.
    glued_towns = set() if (use_conv or use_area) else _glued_towns(rows, header_idx, vendor_c)

    def _set_party(text):
        # "-KLM COSMOCOR"-style leading-hyphen band = the COMPANY/division sub-band
        # printed under each party (Busy "Report For : SALE-S/R" grouping, UMA).
        # It must never overwrite the party above it. Real party bands never start
        # with "-" in this layout (the -L/-<area> conventions are trailing).
        if text.lstrip().startswith("-"):
            return None
        if use_conv:
            if _is_page_noise(text, vendor_c):
                return None            # repeated header/title/vendor/footer — not a party
            return _split_location(text)
        if use_area:
            return _split_area(text)
        if glued_towns:
            return _split_glued_town(text, glued_towns)
        return text, ""

    records = []
    current_party = ""
    current_loc = ""
    for raw in rows[header_idx + 1:]:
        cells = [cell_text(c) for c in raw]
        distinct = [c for c in cells if c]
        if not distinct:
            continue
        # Every vendor's report reprints a page-break block (vendor banner, report
        # title, the spaced "D E S C R I P T I O N" column header, "Continued..").
        # Skip it up front so it can neither become a fake party band nor a bogus
        # product line. Checked on the JOINED row text so a header split across real
        # columns ("D E S C R I P T I O N" | "QTY." | ...) is caught too. Was gated
        # behind use_conv, so non-Local files (SHREE HARISH) leaked at every page.
        if _is_page_noise(_ws(" ".join(cells)), vendor_c):
            continue

        if len(set(distinct)) == 1:
            # single-column / merged text line: split into tokens and read trailing numbers
            text = _ws(distinct[0])
            if not text or _DASHES_RE.match(text) or _is_total_label(text):
                continue
            if use_conv:
                # This vendor prints the FREE column as a bare "-" (= 0) and omits the
                # trailing "( % )" on most lines. The generic right-aligned reader below
                # halts the numeric pop at the "-", dropping QTY and every free="-" line.
                # Treat "-" as 0 so QTY is captured, then map the trailing run LEFT-to-right
                # onto QTY / FREE / RATE / AMOUNT (any extra "( % )" tail is ignored).
                raw_toks = text.split()
                conv = ["0" if t == "-" else t for t in raw_toks]
                k = len(conv)
                while k > 0 and _is_num(conv[k - 1]):
                    k -= 1
                vnums = [conv[j].replace(",", "") for j in range(k, len(conv))]
                if len(vnums) >= 4:
                    product = " ".join(raw_toks[:k]).strip()
                    if product and current_party:
                        rec = {"party_name": current_party, "product_name": product,
                               "qty": vnums[0], "free_qty": vnums[1],
                               "rate": vnums[2], "amount": vnums[3]}
                        if current_loc:
                            rec["party_location"] = current_loc
                        records.append(rec)
                elif not vnums:
                    split = _set_party(text)
                    if split is not None:
                        current_party, current_loc = split
                continue
            toks = text.split()
            nums = []
            while toks and _is_num(toks[-1]):
                nums.insert(0, toks.pop())
            if len(nums) >= 3:
                # any leading numbers beyond the value columns belong to the product name
                extra = nums[:len(nums) - ncol] if len(nums) > ncol else []
                product = " ".join(toks + extra).strip()
                if product and current_party:
                    records.append(_emit(product, [n.replace(",", "") for n in nums], current_party, current_loc))
            elif not nums:
                split = _set_party(text)
                if split is not None:
                    current_party, current_loc = split
            elif (len(nums) == 2 and "free_qty" in cols and toks
                  and toks[-1] == "-" and _is_num(toks[-2])
                  and re.search(r"[A-Za-z]", " ".join(toks[:-2]))):
                # Product line whose FREE column is a bare "-" (= 0) with no trailing
                # "( % )": the dash halts the numeric pop, leaving only rate+amount
                # (nums == 2) so the >=3 test missed and the row was swallowed as a
                # party band. Reclaim it: qty = number just before the dash, free = 0,
                # the two popped nums = rate, amount. A real party band never ends
                # "<number> -" (its trailing MARG code leaves a letter token), so this
                # additive branch cannot steal a band.
                product = " ".join(toks[:-2]).strip()
                if product and current_party:
                    rec = {"party_name": current_party, "product_name": product,
                           "qty": toks[-2].replace(",", ""), "free_qty": "0",
                           "rate": nums[0].replace(",", ""), "amount": nums[1].replace(",", "")}
                    if current_loc:
                        rec["party_location"] = current_loc
                    records.append(rec)
            elif toks and re.search(r"[A-Za-z]", " ".join(toks)):
                # A party band whose name carries a trailing MARG party-code number
                # (e.g. "AGRAWAL CHEMIST U N-INDORE 3", "ALSHIFA CHEMIST-INDORE 8"):
                # popping the trailing digit(s) leaves 1-2 numbers, fewer than a real
                # product line's >=3 value columns (QTY/RATE/AMOUNT at minimum, +FREE here).
                # Those bands previously fell through and were DROPPED, losing the party and
                # all its products. A genuine product line always has >=3 trailing numbers, so
                # this branch cannot steal one. Restore the FULL band text (name + code) as
                # the party via the normal band handler.
                if not _is_total_label(text) and not _is_page_noise(text, vendor_c):
                    split = _set_party(text)
                    if split is not None:
                        current_party, current_loc = split
        else:
            # real columns: description in the first cell, figures in the rest
            product = _ws(cells[0])
            if not product or _DASHES_RE.match(product) or _is_total_label(product):
                continue
            # Keep a bare "-" (QTY/FREE printed as a dash = 0) as a value so the right-
            # aligned columns don't shift and drop QTY. Files without "-" are unaffected:
            # numeric cells append exactly as before, only the dash adds a "0".
            #
            # An *interior* blank value cell (one with a non-empty value cell to its
            # right) is likewise a rendered-empty column, not a missing column: some
            # MARG exports leave the QTY cell blank when the line is a straight sale
            # (e.g. DERMA "MFSONE CREAM 30GM" | '' | '-' | 159.35 | 318.7). Treating it
            # as "0" keeps the right-aligned QTY/FREE/RATE/AMOUNT slots from shifting and
            # dropping QTY. Trailing blanks (no value cell to the right — e.g. the RATE
            # cell blanked on TOTAL rows) carry no data and are still ignored, so files
            # without interior blanks stay byte-identical.
            tail = cells[1:]
            last_val = max((i for i, c in enumerate(tail)
                            if _num_val(c) or c.strip() == "-"), default=-1)
            vals = []
            for i, c in enumerate(tail):
                v = _num_val(c)
                if v:
                    vals.append(v)
                elif c.strip() == "-":
                    vals.append("0")
                elif c.strip() == "" and i < last_val:
                    vals.append("0")
            if vals and current_party:
                records.append(_emit(product, vals, current_party, current_loc))
            elif not vals:
                split = _set_party(product)
                if split is not None:
                    current_party, current_loc = split

    detected = {"D E S C R I P T I O N": "product_name", "QTY.": "qty",
                "FREE": "free_qty", "RATE": "rate", "AMOUNT": "amount"}
    return records, detected
