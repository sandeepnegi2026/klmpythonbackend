import re

from extractors.party_pdf.party_area import extract_party_and_area


def _split_party_area(cur_raw):
    """extract_party_and_area(busy_tally) splits on the LAST '-', so a heading
    whose area carries a numeric locality suffix ("ADITYA MEDICALS-PATNA-2",
    "MEENA MEDICAL HALL-PATNA 20") lands as name="...-PATNA"/area="2" (or
    name="...", area="PATNA 20"). Recover the intended split: the tail after the
    LAST '-' of shape "<CITY>[<sep><digits>]" is the area. Only re-splits
    headings that match this exact numeric-locality shape, so normal alpha-area
    headings fall through to the shared helper untouched."""
    m = re.match(
        r"^(?P<name>.+?)\s*-\s*(?P<area>[A-Z][A-Za-z]*(?:[ -]\d+)?)$", cur_raw
    )
    if m and re.search(r"\d", m.group("area")):
        name = m.group("name").strip()
        area = re.sub(r"\s*-\s*", "-", m.group("area").strip())
        if name:
            return name, area
    return extract_party_and_area(cur_raw, "busy_tally")


def parse_busy_tally(text):
    H = ["Party Name", "Area", "Product Name", "Qty", "Free", "Rate", "Amount", "Vendor Name"]
    pat6 = re.compile(r"^(.+?)\s+(\d+)\s+([\d-]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*$")
    pat5 = re.compile(r"^(.+?)\s+([\d-]+)\s+([\d-]+)\s+([\d.]+)\s+([\d.]+)\s*$")
    # Additive fallback for detail lines with a DECIMAL qty (e.g. "5.50") or a
    # NEGATIVE qty (e.g. "-1", return lines with negative amounts), which
    # pat5/pat6 reject (integer-only qty, no leading minus). Tried ONLY on lines
    # every existing branch below already fails to match, so every line parsed
    # today parses identically (do NOT broaden pat5/pat6 -- that regressed 18
    # party PDFs and was reverted). Shape-strict: qty must be decimal or
    # negative, rate/amount must carry exactly 2 decimals, which keeps
    # addresses, headers and band labels out.
    _qty_frac_neg = r"(-\d+(?:\.\d{1,3})?|\d+\.\d{1,3})"
    _free_opt = r"(-|-?\d+(?:\.\d{1,3})?)"
    _money = r"(-?\d+\.\d{2})"
    pat6_frac = re.compile(
        r"^(.+?)\s+" + _qty_frac_neg + r"\s+" + _free_opt + r"\s+" + _money + r"\s+" + _money + r"\s+" + _money + r"\s*$"
    )
    pat5_frac = re.compile(
        r"^(.+?)\s+" + _qty_frac_neg + r"\s+" + _free_opt + r"\s+" + _money + r"\s+" + _money + r"\s*$"
    )
    # INTEGER-qty + DECIMAL-free rows (KLMPARTY "K-DOX 10 CAP 17 1.50 88.12 1498.05
    # 0.27"): pat6 free=[\d-]+ rejects the decimal free, and pat6_frac needs a
    # decimal/negative QTY, so an integer-qty line with a half-scheme fractional
    # free falls in the gap and is silently dropped. Shape-strict (integer qty,
    # decimal free, 2-dp money tail) and tried ONLY after every pattern above
    # fails, so no line parsed today changes.
    _decfree = r"(\d+\.\d{1,3})"
    pat6_intqty_decfree = re.compile(
        r"^(.+?)\s+(\d+)\s+" + _decfree + r"\s+" + _money + r"\s+" + _money + r"\s+" + _money + r"\s*$"
    )
    pat5_intqty_decfree = re.compile(
        r"^(.+?)\s+(\d+)\s+" + _decfree + r"\s+" + _money + r"\s+" + _money + r"\s*$"
    )
    # COLON-FUSED qty cell (JUNE-2026 Busy scheme split, "KLCLAV 625 10,S 3:0 0
    # 143.36 430.09 0.22"): the qty column prints as "<qty>:<free>" glued by a
    # colon, followed by a standalone scheme token, then rate/amount/(%). pat6
    # qty=(\d+) halts at the colon so the whole row is dropped. Take qty/free from
    # the two colon parts; the standalone scheme token is consumed but unused.
    pat6_colon = re.compile(
        r"^(.+?)\s+(-?\d+):(-?\d+)\s+[\d.-]+\s+" + _money + r"\s+" + _money + r"\s+" + _money + r"\s*$"
    )
    pat5_colon = re.compile(
        r"^(.+?)\s+(-?\d+):(-?\d+)\s+[\d.-]+\s+" + _money + r"\s+" + _money + r"\s*$"
    )

    has_pct = bool(re.search(r'\b(PCT|DISC\.?|DISCOUNT)\b|\( ?% ?\)', text, re.IGNORECASE))

    # INVOICE-DETAIL SUB-LINE guard (S.P.D. "PARTY / ITEM WISE SALES SUMMARY").
    # In this dialect each product AGGREGATE line (kept via pat6, ends in the
    # trailing "( % )" value) is followed by one line PER SOURCE INVOICE:
    #   "SPD003997 16-05 EH512 1 - 139.28 133.71"
    #   <invoice-no> <DD-MM> <batch> <qty> <free> <rate> <amount>
    # These carry only 4 numbers (no % column) so pat5 matches them and each is
    # emitted as a PHANTOM product row whose name is the invoice code -- doubling
    # every qty/value (sum of kept rows == printed GRAND TOTAL, sum WITH these ==
    # ~2x). The signature is unambiguous: a leading alnum invoice CODE (letters
    # AND a digit, no spaces) whose SECOND token is a DD-MM/DD/MM date, then a
    # batch token and the numeric tail. A real product aggregate line's second
    # token is NEVER a bare date, so no product row can match. Corpus-wide this
    # signature appears in ZERO other busy_tally files (probed all 156) and ZERO
    # busy_tally baselines, so skipping it changes only this file.
    inv_detail = re.compile(
        r"^\S*[A-Za-z]\S*\d\S*\s+\d{2}[-/]\d{2}\s+\S+\s+"
        r"[\d-]+\s+[\d-]+\s+[\d.]+\s+[\d.]+\s*$"
    )

    rows, cur_raw = [], ""
    # Decimal/negative-qty rescue rows (pat*_frac below) are appended to `rows`
    # IN DOCUMENT ORDER, interleaved with their party's integer rows, so a party
    # that mixes integer and decimal/return lines stays in ONE contiguous block
    # (previously they were deferred to the end, splitting such parties in two).
    # They do NOT flip `has_int_row`: a file with ZERO strict integer-qty rows is
    # a decimal-only sibling (e.g. VIPIN "party / item wise", correctly handled by
    # party_item_summary_nofree via pdf_io's empty-result fallback), so we return
    # EMPTY for it instead of hijacking that routing with a partial parse.
    has_int_row = False
    skips = [
        "OLD ",
        "Phone",
        "Licence",
        "GSTIN",
        "PARTY",
        "Report",
        "Company",
        "D E S C",
        "GRAND",
        "***",
        "Continued",
        "Page",
        "TOTAL",
        "-----",
    ]
    vendor_line = text.strip().split("\n")[0].strip() if text.strip() else ""
    if vendor_line:
        skips.append(vendor_line[:20])
    pat_code_party = re.compile(r"^\d{3,6}\s+([A-Z].*?)\s*$")
    # Numeric-locality / leading-dot party heading, e.g. "ASHOK MEDICAL HALL-
    # PATNA-4", "MEENA MEDICAL HALL-PATNA 20", ".RAKESH AGENCY-PATNA-4". The
    # tail after the LAST hyphen is a COMPACT alpha city + optional numeric
    # suffix, which a multi-clause vendor address ("...BLOCK-C, DAWA BAZAR,
    # UJJAIN (M.P.) 456010") can never match.
    pat_numeric_area_party = re.compile(
        r"^[.A-Z0-9][A-Z0-9\s&.,()\[\]/*'_-]+-[A-Z][A-Za-z]*(?:[ -]\d+)?$"
    )
    _money_anywhere = re.compile(r"\d+\.\d{2}")
    for line in text.split("\n"):
        # (cid:N) is a raw-glyph artifact; pdf_io normally decodes it upstream, but
        # strip any literal residue here too so direct callers behave the same.
        s = re.sub(r"\(cid:\d+\)", "", line).strip()
        if not s or any(s.startswith(sk) for sk in skips):
            continue
        # Drop per-invoice detail sub-lines (see inv_detail note above). Gated on
        # the structural code+DD-MM signature so it never touches a product row.
        if inv_detail.match(s):
            continue
        # Busy/Marg flags a "new"/starred customer with a single leading '*' on
        # the party heading ("*MANNI MEDICAL HALL-JABALPUR."); sibling headings
        # carry none, so only the first party is starred and every band branch
        # below (first char [A-Z0-9]/[.A-Z0-9]) rejects it -> its rows inherit the
        # empty/previous party. Strip that one marker so the '*' isn't kept in the
        # name and the NAME-AREA checks see the bare heading. Guarded: a letter
        # must follow (so '***' separators — already skipped — and starred numeric
        # rows can't match) and the line must NOT be a data row (data rows keep
        # their leading '*' inside the product name via pat*).
        m_star = re.match(r"^\*\s*([A-Za-z].*)$", s)
        if m_star and not (
            pat6.match(s) or pat5.match(s) or pat6_frac.match(s) or pat5_frac.match(s)
        ):
            s = m_star.group(1).strip()
        # Party heading prefixed with a numeric account code, e.g.
        # "00350 SAIF MEMORIAL M/S STORE KALABURAG" (Busy/Tally code-prefixed
        # parties). Strip the code; guard against numeric data rows.
        m_code = pat_code_party.match(s)
        if m_code and not pat6.match(s) and not pat5.match(s):
            cur_raw = m_code.group(1).strip()
            continue
        # NAME-AREA party band. Leading char may be a digit (e.g. "24*7 PHARMACY
        # (LIG)-INDORE") and names can carry *, ', _ (e.g. "FRIEND'S PHARMACY",
        # "...(SCH NO.54)_", "...DRU.*(KAML"). The trailing "-<AREA>" anchor keeps
        # data rows (which end in numbers) out, so widening the class is safe.
        if re.match(r"^[A-Z0-9][A-Z0-9\s&.,()\[\]/*'_-]+-[A-Z][A-Z0-9\[\]]+$", s):
            cur_raw = s
            continue
        # NAME-AREA-<DAYTAG/SEC> party band carrying DIGITS/parens in the trailing
        # segments, e.g. "AMIT MEDICAL STORE-SEC-4-SEC-4",
        # "CUB PHARMACY PLUS-SEC-31-MONDAY(DLF,CP)",
        # "DELHI CHILDREN CLINIC-OLD RLY-TUESDAY(JR,RR)". The alpha-area bands
        # above reject these (their AREA class forbids digits/parens) so the
        # heading fell through to the data patterns (which it also fails),
        # silently keeping cur_raw on the PREVIOUS party -> the first such party
        # is dropped entirely (empty party_name) and every product under a later
        # such heading inherits the WRONG party. Tightly gated so it can never
        # swallow a multi-clause vendor ADDRESS line ("231, 2ND FLOOR, BLOCK-C,
        # DAWA BAZAR, UJJAIN (M.P.) 456010") or a product row
        # ("NIOCLEAN AD 15GM 0 0 0.00"): require a LETTER first char (addresses
        # start with a house-number digit), an internal hyphen, NO decimal money
        # anywhere (product rows carry a X.XX amount), and NO comma OUTSIDE
        # parentheses (addresses use comma-separated clauses; day-tags keep their
        # comma inside "(DLF,CP)"), plus NOT a data-row pattern.
        if (
            "-" in s
            and re.match(r"^[A-Z][A-Z0-9\s&.,()\[\]/*'_-]*-[A-Z0-9][A-Z0-9\s&.,()\[\]/*'_-]*$", s)
            and "," not in re.sub(r"\([^)]*\)", "", s)
            and not _money_anywhere.search(s)
            and not pat6.match(s)
            and not pat5.match(s)
            and not pat6_frac.match(s)
            and not pat5_frac.match(s)
            and len(s) > 5
        ):
            cur_raw = s
            continue
        # NAME-AREA party band whose AREA carries a numeric locality suffix
        # ("ASHOK MEDICAL HALL-PATNA-4", "MEENA MEDICAL HALL-PATNA 20") or begins
        # with a leading account dot (".RAKESH AGENCY-PATNA-4"). The alpha-only
        # bands above require an ALL-alpha area, so these were skipped and their
        # rows absorbed into the previous party. Gated on NO decimal money + NOT a
        # data row; the COMPACT alpha-city+optnum tail anchor keeps multi-clause
        # addresses out (their post-hyphen tail is not a single city token).
        if (
            not _money_anywhere.search(s)
            and not pat6.match(s)
            and not pat5.match(s)
            and pat_numeric_area_party.match(s)
        ):
            cur_raw = s
            continue
        if (
            re.match(r"^[A-Z][A-Z\s&.,()\[\]/-]+$", s)
            and not pat6.match(s)
            and not pat5.match(s)
            and len(s) > 5
            and not re.match(r"^[A-Z]+\s+\d", s)
        ):
            cur_raw = s
            continue
        # A data row may carry a stray glyph decoded from a control char (pdf_io's
        # _decode_cid maps e.g. (cid:12) -> ')'), which lands after the final number
        # and breaks the end-anchored patterns, silently dropping the row. Strip a
        # dangling bracket that immediately follows a digit. Reached only AFTER the
        # band checks above, so party headings ending in ')' are left untouched.
        s = re.sub(r"(?<=\d)[)\]]+\s*$", "", s)
        if has_pct:
            m = pat6.match(s)
            if m:
                name, area = _split_party_area(cur_raw)
                rows.append(
                    [
                        name,
                        area,
                        m.group(1).strip(),
                        m.group(2),
                        m.group(3).replace("-", "0"),
                        m.group(4),
                        m.group(5),
                        vendor_line,
                    ]
                )
                has_int_row = True
                continue
        m5 = pat5.match(s)
        if m5:
            name, area = _split_party_area(cur_raw)
            rows.append(
                [
                    name,
                    area,
                    m5.group(1).strip(),
                    m5.group(2).replace("-", "0"),
                    m5.group(3).replace("-", "0"),
                    m5.group(4),
                    m5.group(5),
                    vendor_line,
                ]
            )
            has_int_row = True
            continue
        # DECIMAL/NEGATIVE-qty fallback: reached only when every pattern above
        # failed, i.e. on lines otherwise silently dropped. Appended in place so
        # the row stays with its party (see has_int_row note above).
        mf = pat6_frac.match(s) if has_pct else pat5_frac.match(s)
        if mf:
            name, area = _split_party_area(cur_raw)
            free = mf.group(3)
            rows.append(
                [
                    name,
                    area,
                    mf.group(1).strip(),
                    mf.group(2),
                    "0" if free == "-" else free,
                    mf.group(4),
                    mf.group(5),
                    vendor_line,
                ]
            )
            continue
        # INTEGER-qty + DECIMAL-free fallback (see pattern note). Reached only when
        # every branch above failed, i.e. on otherwise-dropped half-scheme rows.
        mi = pat6_intqty_decfree.match(s) if has_pct else pat5_intqty_decfree.match(s)
        if mi:
            name, area = _split_party_area(cur_raw)
            rows.append(
                [name, area, mi.group(1).strip(), mi.group(2), mi.group(3),
                 mi.group(4), mi.group(5), vendor_line]
            )
            continue
        # COLON-FUSED qty-cell fallback (see pattern note). qty/free come from the
        # two colon parts; a '-' free is normalised to 0.
        mc = pat6_colon.match(s) if has_pct else pat5_colon.match(s)
        if mc:
            name, area = _split_party_area(cur_raw)
            free = mc.group(3)
            rows.append(
                [name, area, mc.group(1).strip(), mc.group(2),
                 "0" if free == "-" else free, mc.group(4), mc.group(5), vendor_line]
            )
            continue
    # A file with ZERO strict integer-qty rows is a decimal-only sibling, not a
    # busy_tally report -> return empty so pdf_io routes it to its dedicated parser
    # instead of hijacking with a partial (decimal-only) parse.
    if not has_int_row:
        return H, []
    return H, rows


def parse_busy_tally_itemwise(text):
    H = ["Party Name", "Area", "Product Name", "Qty", "Free", "Rate", "Amount", "Vendor Name"]
    pat5 = re.compile(r"^(.+?)\s+([\d.]+|-)\s+([\d.]+|-)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*$")
    pat4 = re.compile(r"^(.+?)\s+([\d.]+|-)\s+([\d.]+|-)\s+([\d.]+)\s+([\d.]+)\s*$")
    
    has_pct = bool(re.search(r'\b(PCT|DISC\.?|DISCOUNT)\b|\( ?% ?\)', text, re.IGNORECASE))
    
    rows, cur_product = [], ""
    skips = [
        "Phone",
        "Licence",
        "GSTIN",
        "GST NO",
        "ITEM /",
        "Report",
        "Company",
        "D E S C",
        "GRAND",
        "***",
        "Continued",
        "Page",
        "TOTAL",
        "-----",
        "Amount =",
    ]
    vendor_line = text.strip().split("\n")[0].strip() if text.strip() else ""
    if vendor_line:
        skips.append(vendor_line[:20])
    for line in text.split("\n"):
        s = line.strip()
        if not s or any(s.startswith(sk) for sk in skips):
            continue
        
        # Try 5-column match first (6 groups total)
        if has_pct:
            m = pat5.match(s)
            if m:
                name, area = extract_party_and_area(m.group(1).strip(), "busy_tally")
                qty = m.group(2)
                free = m.group(3)
                rows.append(
                    [
                        name,
                        area,
                        cur_product,
                        qty if qty != "-" else "0",
                        free if free != "-" else "0",
                        m.group(4),
                        m.group(5),
                        vendor_line,
                    ]
                )
                continue
            
        # Try 4-column match as fallback
        m = pat4.match(s)
        if m:
            name, area = extract_party_and_area(m.group(1).strip(), "busy_tally")
            qty = m.group(2)
            free = m.group(3)
            rows.append(
                [
                    name,
                    area,
                    cur_product,
                    qty if qty != "-" else "0",
                    free if free != "-" else "0",
                    m.group(4),
                    m.group(5),
                    vendor_line,
                ]
            )
            continue
            
        if not re.match(r"^TOTAL\b", s, re.I):
            cur_product = s
    return H, rows
