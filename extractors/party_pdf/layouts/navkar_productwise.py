import re


def parse_navkar_productwise(text):
    """'Product wise sale list' (NAVKAR APOTEK style). Customer names sit on a
    bare heading line; each sale row is
    '<date> <bill-no> <product> <HSN> <pack> <batch> <exp-date> <qty>'.
    A division/company line ('KLM LABORATORIES PED') and 'Customer Total'
    delimiters separate blocks. The report is quantity-only (no rate/amount),
    so only Qty is captured. A trailing ledger section (lines that are not
    date-prefixed rows) is naturally ignored by the row regex.

    The PRIMARY regex (unchanged) matches the clean rows. Some rows are dropped
    by it because the glyph-packed source mangles the middle columns:
      * bill number is a bare digit run ('714 TODDRUB OINT') with no letter prefix
      * pack has an interior space ('60 ML') or is glued to the batch ('100GMKI510')
        so the single-token pack/batch capture misaligns
      * pack+HSN are glyph-interleaved ('100M3L3049930') so no clean 6-8 digit HSN
        run exists
    These are recovered by ORDERED FALLBACK regexes tried ONLY when the primary
    fails, so every row the primary already matches is byte-for-byte unchanged.
    """
    H = ["Party Name", "Product Name", "Pack", "Batch", "Inv No", "Date", "Qty"]
    rows, party = [], ""
    # PRIMARY — clean 8-field row (unchanged).
    ROW = re.compile(
        r"^(\d{2}-\d{2}-\d{4})\s+([A-Z]{2,6}\s*\d+)\s+(.+?)\s+(\d{6,8})\s+"
        r"(\S+)\s+(\S+)\s+(\d{2}-\d{2}-\d{4})\s+(-?\d+)$"
    )
    # FB1 — bill number may be a bare digit run (drop the letter requirement).
    FB1 = re.compile(
        r"^(\d{2}-\d{2}-\d{4})\s+([A-Z]{0,6}\s*\d+)\s+(.+?)\s+(\d{6,8})\s+"
        r"(\S+)\s+(\S+)\s+(\d{2}-\d{2}-\d{4})\s+(-?\d+)$"
    )
    # FB2 — clean 6-8 digit HSN present, but the pack/batch region is one blob of
    # MULTIPLE tokens (spaced pack '60 ML' or pack glued to batch '100GMKI510').
    FB2 = re.compile(
        r"^(\d{2}-\d{2}-\d{4})\s+([A-Z]{0,6}\s*\d+)\s+(.+?)\s+(\d{6,8})\s+"
        r"(.+?)\s+(\d{2}-\d{2}-\d{4})\s+(-?\d+)$"
    )
    # FB3 — HSN is glyph-interleaved (no clean 6-8 digit run); anchor only on
    # date+bill at the front and exp-date+qty at the tail, keep the whole middle
    # as the product blob (a trailing HSN/pack/batch tail is stripped below).
    FB3 = re.compile(
        r"^(\d{2}-\d{2}-\d{4})\s+([A-Z]{0,6}\s*\d+)\s+(.+?)\s+"
        r"(\d{2}-\d{2}-\d{4})\s+(-?\d+)$"
    )
    # trailing glyph tail on an FB3 product blob: '<mangled-hsn> <pack> <batch>'
    # e.g. 'SOFIDEW BABY MOIST LOTION 100M3L3049930 100ML AC3602'. Peel the last
    # up-to-3 tokens that carry a mangled HSN/pack/batch (contain a digit AND a
    # letter, or are a pure pack like '100ML'), leaving the readable name.
    TAIL = re.compile(r"^(?:[0-9]+[A-Za-z]|[A-Za-z]*\d{4,}|\d+[A-Z]{2,}\d*)")

    SKIP = (
        "product wise sale list",
        "date bill no product",
        "customer total",
        "page no",
        "grand total",
        "company total",
        "opening",
        "closing",
    )

    def _emit(date, bill, prod, pack, batch, qty):
        rows.append([
            party,
            prod.strip(),
            pack,
            batch,
            bill.strip(),
            date,
            qty,
        ])

    for raw in text.split("\n"):
        s = re.sub(r"\s+", " ", raw.strip())
        if not s:
            continue
        sl = s.lower()

        m = ROW.match(s)
        if m and party:
            _emit(m.group(1), m.group(2), m.group(3),
                  m.group(5), m.group(6), m.group(8))
            continue

        if party:
            m = FB1.match(s)
            if m:
                _emit(m.group(1), m.group(2), m.group(3),
                      m.group(5), m.group(6), m.group(8))
                continue
            m = FB2.match(s)
            if m:
                # pack/batch blob: first token -> pack, rest -> batch.
                blob = m.group(5).split()
                pack = blob[0] if blob else ""
                batch = " ".join(blob[1:]) if len(blob) > 1 else ""
                _emit(m.group(1), m.group(2), m.group(3),
                      pack, batch, m.group(7))
                continue
            m = FB3.match(s)
            if m:
                prod = m.group(3)
                # strip a trailing mangled HSN/pack/batch tail from the name
                toks = prod.split()
                while len(toks) > 1 and TAIL.match(toks[-1]):
                    toks.pop()
                _emit(m.group(1), m.group(2), " ".join(toks),
                      "", "", m.group(5))
                continue

        if any(k in sl for k in SKIP):
            continue
        # division / company header (e.g. 'KLM LABORATORIES PED') — not a party
        if "laboratories" in sl:
            continue
        # trailing ledger lines carry bill codes like 'KLM/2015/2526' — skip
        if re.search(r"\b[A-Z]+/\d+/\d+\b", s):
            continue
        # a bare uppercase customer heading becomes the current party
        if re.search(r"[A-Za-z]", s) and not re.search(r"\d{2}-\d{2}-\d{4}", s):
            party = s

    return H, rows
