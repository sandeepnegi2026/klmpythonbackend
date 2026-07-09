import re

from extractors.party_pdf.party_area import extract_party_and_area


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

    has_pct = bool(re.search(r'\b(PCT|DISC\.?|DISCOUNT)\b|\( ?% ?\)', text, re.IGNORECASE))

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
    for line in text.split("\n"):
        # (cid:N) is a raw-glyph artifact; pdf_io normally decodes it upstream, but
        # strip any literal residue here too so direct callers behave the same.
        s = re.sub(r"\(cid:\d+\)", "", line).strip()
        if not s or any(s.startswith(sk) for sk in skips):
            continue
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
                name, area = extract_party_and_area(cur_raw, "busy_tally")
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
            name, area = extract_party_and_area(cur_raw, "busy_tally")
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
            name, area = extract_party_and_area(cur_raw, "busy_tally")
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
