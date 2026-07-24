import re

from extractors.party_pdf.parse_common import _sk


def _marg_register_tail(tail):
    # The party name (and an occasional trailing "-NN" fragment) can be glued
    # straight onto the amount with no space ("...5332.28MR.(ALL)-36"): a bare
    # number scan would then read that trailing "36" as the amount and drop the
    # real 5332.28. Cut the tail at the first letter so only the true numeric
    # columns survive, then read SIGNED numbers so sales-return rows keep their
    # negative qty/amount (Marg prints returns with a leading '-'). Rows whose
    # glued party carries no trailing digit — and rows with a separate party line
    # (numeric-only tail) — are unaffected: the amount already sat before the first
    # letter, so truncation is a no-op there and the signed scan matches the old
    # unsigned scan token-for-token.
    numeric = re.split(r"[A-Za-z]", tail or "", maxsplit=1)[0]
    nums = [n.rstrip(".") for n in re.findall(r"-?\d[\d.]*", numeric)]
    qty = nums[0] if nums else ""
    # A glyph-scrambled export can glue a letter-less salesman token onto the
    # amount — a phone ("...293.05CHIRAG-9825522022") or a bare code
    # ("...213.21--999") — so the trailing number is an integer with no paise.
    # A real Marg line amount ALWAYS carries paise decimals, so when the last
    # number has no decimal point the amount is the last decimal-bearing number
    # instead. (Generalizes the old 6+-digit phone guard: "-999" is the same
    # disease at 4 chars.) Rows whose tail holds no decimal at all keep the old
    # last-number read.
    amt_idx = len(nums) - 1
    amount = nums[-1] if len(nums) >= 2 else ""
    if amount and "." not in amount:
        dec_idxs = [i for i, n in enumerate(nums) if "." in n]
        if dec_idxs:
            amt_idx = dec_idxs[-1]
            amount = nums[amt_idx]
    # The middle columns (between Qty and Amount) are S.Qty, Disc% and Sch Disc, all
    # optional and blank-collapsed in the flattened text, so their positions cannot be
    # read by index alone. Disambiguate by shape: S.Qty is a whole-unit free/scheme
    # count and always prints as an integer ("2.", "10."), while Disc% and Sch Disc
    # always carry a fractional part ("5.0", "3.0", "-50.46"). So the free qty is the
    # first pure-integer middle column; every decimal middle is a discount column.
    # This stops a lone "5.0" Disc% (3-number rows) or an all-negative return row's
    # discount from being mis-read as free qty, and it is never worse than the old
    # blind positional read on any clean row (the integer S.Qty still lands first).
    # Middles run only up to the resolved amount position, so a glued trailing
    # code is not mistaken for a column.
    s_qty = disc = sch = ""
    disc_cols = []
    for m in nums[1:amt_idx]:
        if not s_qty and re.fullmatch(r"-?\d+", m):
            s_qty = m
        else:
            disc_cols.append(m)
    if disc_cols:
        disc = disc_cols[0]
    if len(disc_cols) > 1:
        sch = disc_cols[1]
    return qty, s_qty, disc, sch, amount


def _marg_register_item_match(s):
    # GST is anchored to exactly d+.dd here (all live Marg GSTs print with two
    # paise decimals: 0.00/5.00/18.00). The old loose "[\d.]+" let a digit-leading
    # glued batch feed its leading digits into the GST: "5.0025S3GTB425" parsed as
    # gst=5.0025 / batch=S3GTB425 (truth: 5.00 / 25S3GTB425) on 19 VENUS rows,
    # and because this primary wins, the correct glued-batch fallbacks below never
    # saw the line. Anchoring pushes those lines to the fallbacks, which split them
    # right; every line with a real 2-decimal GST parses byte-identically.
    glued = re.match(
        r"^(.+?)\s+(\d+\.\d{2})([A-Z][A-Z0-9]+)\s+(\S+)\s+(\d{2}-\d{2}-\d{2})\s+(.+)$",
        s,
    )
    if glued:
        return {
            "product": glued.group(1).strip(),
            "gst": glued.group(2),
            "batch": glued.group(3),
            "inv_no": glued.group(4),
            "date": glued.group(5),
            "tail": glued.group(6),
        }
    spaced = re.match(
        r"^([\d.]+)\s+([A-Z][A-Z0-9]+)\s+(\S+)\s+(\d{2}-\d{2}-\d{2})\s+(.+)$",
        s,
    )
    if spaced:
        return {
            "product": "",
            "gst": spaced.group(1),
            "batch": spaced.group(2),
            "inv_no": spaced.group(3),
            "date": spaced.group(4),
            "tail": spaced.group(5),
        }
    # Same d+.dd anchor as `glued` above: the loose form swallowed a whole glued
    # numeric batch as the "GST" ("5.00250463 SZ3876 ..." -> gst=5.00250463,
    # batch lost); anchored, that line falls through to cont_glued which splits
    # it correctly (gst 5.00, batch 250463).
    inv_only = re.match(
        r"^(\d+\.\d{2})\s+(\S+)\s+(\d{2}-\d{2}-\d{2})\s+(.+)$",
        s,
    )
    if inv_only:
        return {
            "product": "",
            "gst": inv_only.group(1),
            "batch": "",
            "inv_no": inv_only.group(2),
            "date": inv_only.group(3),
            "tail": inv_only.group(4),
        }
    # Spaced GST+Batch variant (DAHOD PHARMAKON "Mf-Customer-Itemwise"): the item
    # row prints GST, Batch and InvNo as SEPARATE space-delimited tokens
    # ("ZYCOZOL-XL CREAM 5.00 HY505 SZ6253 09-05-26 2. 500.00") instead of gluing
    # the GST onto the batch. Tried LAST, so every line the three patterns above
    # already match is byte-for-byte unaffected; the required dd-mm-yy date +
    # uppercase batch token keep it off party/total/heading lines.
    spaced_prod = re.match(
        r"^(.+?)\s+([\d.]+)\s+([A-Z][A-Z0-9]+)\s+(\S+)\s+(\d{2}-\d{2}-\d{2})\s+(.+)$",
        s,
    )
    if spaced_prod:
        return {
            "product": spaced_prod.group(1).strip(),
            "gst": spaced_prod.group(2),
            "batch": spaced_prod.group(3),
            "inv_no": spaced_prod.group(4),
            "date": spaced_prod.group(5),
            "tail": spaced_prod.group(6),
        }
    # ------------------------------------------------------------------ #
    # Glued-batch fallbacks (VENUS "Mf-Customer-Itemwise"). The four patterns
    # above cannot split a GST glued to a batch that is hyphenated ("IKT-2513"),
    # slashed ("NA/010137") or digit-leading ("25S3GTB427", "0341125D"), and a
    # continuation row prints that glued blob with NO product prefix at all —
    # 386 of this file's 2068 item lines (18.7%) were silently dropped. GST is
    # always exactly d+.dd, so everything glued after those two decimals is the
    # batch. Tried strictly LAST: every line the four patterns above already
    # match is returned before reaching here, byte-for-byte unchanged.
    # ------------------------------------------------------------------ #
    # "\*?" prefix: Marg marks some batches with a star glued between the GST and
    # the batch ("5.00*AJ505"); the star is a marker, not part of the batch id, so
    # it is allowed in the match and stripped from the captured value.
    _BATCH = r"\*?[A-Z0-9][A-Z0-9/.-]*"
    # Continuation row, no product: "18.00AA3605 SZ3918 09-06-26 ..."
    cont_glued = re.match(
        r"^(\d+\.\d{2})(" + _BATCH + r")\s+(\S+)\s+(\d{2}-\d{2}-\d{2})\s+(.+)$",
        s,
    )
    if cont_glued:
        return {
            "product": "",
            "gst": cont_glued.group(1),
            "batch": cont_glued.group(2).lstrip("*").rstrip("."),
            "inv_no": cont_glued.group(3),
            "date": cont_glued.group(4),
            "tail": cont_glued.group(5),
        }
    # Product glued straight onto the GST via "%" / ")":
    # "NIOGLOW FOAMING FACE WASH(18%)18.00AT3601 SZ4256 ..."
    pct_glued = re.match(
        r"^(.+?[%)])(\d+\.\d{2})(" + _BATCH + r")\s+(\S+)\s+(\d{2}-\d{2}-\d{2})\s+(.+)$",
        s,
    )
    if pct_glued:
        return {
            "product": pct_glued.group(1).strip(),
            "gst": pct_glued.group(2),
            "batch": pct_glued.group(3).lstrip("*").rstrip("."),
            "inv_no": pct_glued.group(4),
            "date": pct_glued.group(5),
            "tail": pct_glued.group(6),
        }
    # Spaced product, GST glued to an any-shape batch:
    # "IMXIA 10 5.00IKT-2513 SZ3484 ..." / "KLM D3 60K CAP 5.000341125D SZ3605 ..."
    prod_glued = re.match(
        r"^(.+?)\s+(\d+\.\d{2})(" + _BATCH + r")\s+(\S+)\s+(\d{2}-\d{2}-\d{2})\s+(.+)$",
        s,
    )
    if prod_glued:
        return {
            "product": prod_glued.group(1).strip(),
            "gst": prod_glued.group(2),
            "batch": prod_glued.group(3).lstrip("*").rstrip("."),
            "inv_no": prod_glued.group(4),
            "date": prod_glued.group(5),
            "tail": prod_glued.group(6),
        }
    # Batch printed with an internal space ("SOFIDEW ... 18.00SBP 022 SZ5343 ..."):
    # the glued alpha stem is followed by a short bare-digit fragment BEFORE the
    # invoice+date anchor, so prod_glued/cont_glued read the fragment as the
    # invoice and then fail on the date. Optional product prefix covers the
    # continuation form of the same shape. The extra \d{1,4} token requirement
    # keeps this off every line the patterns above already handle.
    space_batch = re.match(
        r"^(?:(.+?)\s+)?(\d+\.\d{2})(" + _BATCH + r")\s+(\d{1,4})\s+(\S+)\s+"
        r"(\d{2}-\d{2}-\d{2})\s+(.+)$",
        s,
    )
    if space_batch:
        return {
            "product": (space_batch.group(1) or "").strip(),
            "gst": space_batch.group(2),
            "batch": (space_batch.group(3).lstrip("*") + " " + space_batch.group(4)).strip(),
            "inv_no": space_batch.group(5),
            "date": space_batch.group(6),
            "tail": space_batch.group(7),
        }
    # Glyph-interleaved product/GST: pdfplumber x-orders "GEL" and "18.00" into
    # one token — "EKRAN SOFT SILICON SUNCREEN GE1L8.00BD3604 SZ3764 ...".
    # De-interleave: letters(g2) digit(g3) letters(g4) d+.dd(g5) → product word
    # g2+g4 ("GE"+"L"), GST g3+g5 ("1"+"8.00"), batch g6.
    interleaved = re.match(
        r"^(.+?\s)?([A-Z]+)(\d)([A-Z]+)(\d+\.\d{2})(" + _BATCH + r")"
        r"\s+(\S+)\s+(\d{2}-\d{2}-\d{2})\s+(.+)$",
        s,
    )
    # Product glued straight onto the GST with no separator at all — the name's
    # last word (often a pack unit) ends in a letter and the GST digits follow:
    # "COSMO Q AC SUNSCREEN GEL 60GM18.00BJ603 ..." / "NEVMIST MAX LUBRICANT EYE
    # DROPS5.00250337 ...".
    letter_glued = re.match(
        r"^(.+?[A-Za-z])(\d+\.\d{2})(" + _BATCH + r")\s+(\S+)\s+(\d{2}-\d{2}-\d{2})\s+(.+)$",
        s,
    )
    # Both patterns can fire on the same token with different readings:
    #   scrambled "…SUNCREEN GE1L8.00BD3604": interleave -> GEL + 18.00 (right),
    #     letter_glued -> "…GE1L" + 8.00 (wrong);
    #   plain glued "…D3CAP5.00AB123": letter_glued -> D3CAP + 5.00 (right),
    #     interleave -> DCAP + 35.00 (wrong).
    # Discriminate by GST plausibility: a real Marg GST is an Indian slab rate.
    # Prefer the de-interleave ONLY when its reconstructed GST is a slab and the
    # plain reading's is not; in every other case the plain reading wins.
    # When only one reading exists it is taken as-is (never drop a parseable line).
    _STD_GST = {"0.00", "5.00", "12.00", "18.00", "28.00"}
    use_interleaved = False
    if interleaved:
        if not letter_glued:
            use_interleaved = True
        else:
            gst_i = interleaved.group(3) + interleaved.group(5)
            use_interleaved = (gst_i in _STD_GST
                               and letter_glued.group(2) not in _STD_GST)
    if use_interleaved:
        return {
            "product": ((interleaved.group(1) or "") + interleaved.group(2)
                        + interleaved.group(4)).strip(),
            "gst": interleaved.group(3) + interleaved.group(5),
            "batch": interleaved.group(6).lstrip("*").rstrip("."),
            "inv_no": interleaved.group(7),
            "date": interleaved.group(8),
            "tail": interleaved.group(9),
        }
    if letter_glued:
        return {
            "product": letter_glued.group(1).strip(),
            "gst": letter_glued.group(2),
            "batch": letter_glued.group(3).lstrip("*").rstrip("."),
            "inv_no": letter_glued.group(4),
            "date": letter_glued.group(5),
            "tail": letter_glued.group(6),
        }
    return None


def _marg_register_party_parts(raw_line):
    # "-?" so the Credit-Note party headers, whose trailing disc/total pair is
    # negative ("... GHATLODIA- 240 -51.19 -255.94"), also shed their numbers;
    # invoice-section headers only ever carry positive pairs, so for every line
    # the old expression stripped this strips the identical span.
    cleaned = re.sub(r"\s+-?[\d.]+\s+-?[\d.]+\s*$", "", raw_line.strip())
    parts = [part.strip() for part in cleaned.split(",")]
    if len(parts) < 2:
        # Comma-less header (Credit-Note sections drop the ", CITY" suffix):
        # "DR.CHIRAG T SHAH (GHATLODIYA) AC1322 GHATLODIA- 240" /
        # "NARANPURA CHEMIST * 4789 NARANPURA- 405". Name sits before the
        # customer code, area between the code and the trailing "- NNN".
        # Customer-code token shapes. m1 keeps the historical bare-4-digit form
        # ("NARANPURA CHEMIST * 4789 NARANPURA- 405") because its trailing
        # "- NNN" area anchor makes a false split unlikely; m2/m3 have weaker
        # anchors, so their code must be letter-prefixed (AC2308/A00485) or
        # zero-led (0244) — a bare number there is far more likely the party's
        # own name tail ("PHARMACY 365") than a code, and the safe failure is
        # keeping the full name.
        _CODE_STRICT = r"(?:[A-Z]{1,3}\d{3,6}|0\d{3,5})"
        m = re.match(
            r"^(.+?)\s+(?:\*\s+)?(?:[A-Z]{0,3}\d{4,6}|" + _CODE_STRICT + r")\s+(.+?)-\s*\d*$",
            cleaned,
        )
        if m:
            name = m.group(1).strip(" *")
            area = re.sub(r"\s+", " ", m.group(2)).strip(" -")
            if not re.search(r"[A-Za-z]", area):
                area = ""
            return name, area
        # DAHOD shape with a code but NO area ("DR.ASHISH CHODRY - A00680 -"):
        # strip the trailing "- <code> -" decoration off the name.
        m2 = re.match(r"^(.+?)\s*-?\s+\*?\s*" + _CODE_STRICT + r"\s*-?\s*$", cleaned)
        if m2:
            return m2.group(1).strip(" *-"), ""
        # Code followed by a dash-less area / remark tail — observed live 23x in
        # the NEW MEDICAL register and 2x in VENUS credit-note sections:
        # "SOLA PHARMACY (SCIENCE CITY) AC2308 SCIENCE CITY",
        # "MAHAVIR MEDICAL AGENCY 0244 GS.IDAR.C",
        # "RADHESHYAM MEDICAL A00485 MONTHLY CHEQUE PARTY".
        # Name = before the code; the tail lands in area (a remark there is
        # harmless — the win is the clean party name).
        m3 = re.match(r"^(.+?)\s+" + _CODE_STRICT + r"\s+(.+)$", cleaned)
        if m3 and re.search(r"[A-Za-z]{4,}", m3.group(1)):
            area = re.sub(r"\s+", " ", m3.group(2)).strip(" -")
            if not re.search(r"[A-Za-z]", area):
                area = ""
            return m3.group(1).strip(" *"), area
        return cleaned, ""
    name = parts[0]
    area = parts[1]
    area = re.sub(r"\s+[A-Z]?\d{4,6}\s+", " ", area).strip()
    area = re.sub(r"\s+", " ", area)
    # DAHOD "NAME, - A01652 - amt amt": the 2nd comma-part is only the customer
    # code between dashes, so once the code is stripped nothing but "- -" remains.
    # Blank any area left with no letters (a real town/area always has letters);
    # a genuine area name is untouched.
    area = area.strip(" -")
    if not re.search(r"[A-Za-z]", area):
        area = ""
    return name, area


def _marg_register_party_line(s):
    if _marg_register_item_match(s):
        return False
    if _sk(
        s,
        [
            "Item GST",
            "Sales Detail",
            "MF :",
            "Report Date",
            "Amount =",
            # Was the bare prefix "DAHOD" (the stockist letterhead) — which also
            # swallowed the genuine party "DAHOD CHEMIST, DAHOD ..." and pushed
            # its row onto the preceding party. Pin it to the letterhead name.
            "DAHOD PHARMAKON",
            "1ST FLOOR",
            "Invoice",
        ],
    ):
        return False
    if re.match(r"^\d+\.\s", s) or re.match(r"^[\d.]+\s+[\d.]+\s+[\d.]+\s*$", s):
        return False
    # Item-shape guards: a party header NEVER carries a glued GST->batch blob
    # ("18.00AT3601", "5.00*AJ505") or a date token. Without these, an item line
    # whose dd-mm-yy anchor is torn/scrambled (this export family glyph-scrambles;
    # see the interleave pattern) would be accepted as a comma-less party header —
    # dropping the row AND poisoning cur_raw so every following row rebinds to a
    # garbage party. Reject such lines outright; the old behaviour (line simply
    # dropped by the item matcher) is strictly safer than misbinding a section.
    if re.search(r"\d\.\d{2}[*A-Z]", s) or re.search(r"\b\d{2}-\d{2}-\d{2,4}\b", s):
        return False
    # A party header must actually carry a name (kills the numeric section/grand
    # total lines like "2255. 580. -638.91 541122.91").
    if not re.search(r"[A-Za-z]{3,}", s):
        return False
    # A party header always ends "<disc> <total>" with paise decimals
    # ("0.00 9627.10", "-51.19 -255.94"). Requiring the decimals (instead of the
    # old any-two-numbers + comma test) fixes two mis-parses at once: the page-top
    # address line ("37, CELLER, ... Ph:97127 22022. 97378 22022" — trailing
    # integers) no longer qualifies and can no longer steal rows as party "37" /
    # area "CELLER", and the Credit-Note sections' comma-less party headers
    # ("NARANPURA CHEMIST * 4789 NARANPURA- 405 0.00 -166.72"), which the old
    # comma requirement skipped entirely, are now recognised so return rows bind
    # to their real party.
    return bool(re.search(r"-?[\d,]*\d\.\d{2}\s+-?[\d,]*\d\.\d{2}\s*$", s))


def parse_marg_register(text):
    H = [
        "Party Name",
        "Area",
        "Item Name",
        "GST%",
        "Batch",
        "Inv No",
        "Date",
        "Qty",
        # Labelled "S.Qty" in the printed report; it is the free/scheme quantity.
        # "S.Qty" normalizes to "s qty", a synonym of BOTH qty and free_qty, so it
        # collided with the already-claimed Qty column and fell to the raw_ fallback.
        # Emit the unambiguous "Free Qty" so header_match maps it to free_qty.
        "Free Qty",
        "Disc%",
        "Sch Disc",
        "Amount",
    ]
    rows, cur_raw, last_product = [], "", ""
    for line in text.split("\n"):
        s = line.strip()
        if not s:
            continue
        if _marg_register_party_line(s):
            cur_raw = s
            continue
        item = _marg_register_item_match(s)
        if not item:
            continue
        product = item["product"] or last_product
        if item["product"]:
            last_product = item["product"]
        if not product:
            continue
        name, area = _marg_register_party_parts(cur_raw)
        qty, s_qty, disc, sch, amount = _marg_register_tail(item["tail"])
        rows.append(
            [
                name,
                area,
                product,
                item["gst"].rstrip("."),
                item["batch"],
                item["inv_no"],
                item["date"],
                qty,
                s_qty,
                disc,
                sch,
                amount,
            ]
        )
    return H, rows
