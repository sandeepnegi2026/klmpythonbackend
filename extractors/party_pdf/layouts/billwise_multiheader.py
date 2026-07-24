import re

def _despace(s):
    """Join runs of single-char tokens (KLM letter-spaced text) back into words."""
    toks = s.split(' ')
    out = []
    buf = []
    for t in toks:
        if len(t) == 1 and t != '-':
            buf.append(t)
        elif t == '':
            continue
        else:
            if buf:
                out.append(''.join(buf)); buf = []
            out.append(t)
    if buf:
        out.append(''.join(buf))
    return ' '.join(out)

NUM = re.compile(r"-?\d[\d,]*\.\d{2}")

# Layout C row tail: QTY (int)  FREE (int or '-')  RATE (dd.dd)  VALUE (dd.dd),
# anchored at EOL. Used to recover the integer Qty and '-'/int Free that the
# decimal-only NUM regex cannot see. Preserves the negative sign on sales-return
# qty so grand totals reconcile.
_TAIL_C = re.compile(
    r"(?P<qty>-?\d+)\s+(?P<free>-|\d+)\s+"
    r"(?P<rate>-?[\d,]*\.\d{2})\s+(?P<val>-?[\d,]*\.\d{2})\s*$"
)

# A wrapped product-name tail (dosage form) or a bare pack line is a data-row
# continuation, NOT a party heading. Used to stop such lines becoming fake
# parties (e.g. "NEVSOFT CLEANSING" wraps to "LOTION"; "100ML" pack tails).
_FORM_WORDS = {
    "LOTION", "LOTIO", "CREAM", "OINTMENT", "OINT", "GEL", "SHAMPOO", "SYRUP",
    "SOAP", "POWDER", "DROPS", "SOLUTION", "SUSPENSION", "TABLET", "TABLETS",
    "CAPSULE", "CAPSULES", "WASH", "SERUM", "SPRAY", "BAR", "KIT", "TONIC",
    "LIQUID", "SUNSCREEN", "FACE", "MOUTHWASH", "SCRUB", "MASK", "OIL",
}
_PACK_LINE = re.compile(r"^\d+\s*(?:ML|GM|GMS|MG|G|TAB|TABS|CAP|CAPS|LTR|KG|GC|N|S)\.?$", re.I)


def _is_continuation(s):
    t = s.strip()
    if _PACK_LINE.match(t) or t.rstrip(".").upper() in _FORM_WORDS:
        return True
    # A dotted-glue wrapped product tail (single space-less token whose last dotted
    # segment is a dosage form, e.g. "MOISTURE.LOTION", "NEVLON.CREAM") is a data-row
    # continuation, not a party heading.
    if " " not in t and "." in t and t.rstrip(".").split(".")[-1].upper() in _FORM_WORDS:
        return True
    return False

def parse_billwise(text):
    """Header-driven KLM billwise / itemwise parser -> (headers, rows).
    Four layouts distinguished by their column-header line:
      A "Product Name Packing Bill No Bl. Date Qty F.Qty Rate Amount [Value]"  (party=bare area line; mfg-grouped; letter-spaced; per-row Amount = despaced 2nd-last float, or sole float on plain rows)
      B "Bill No. Bill Date Product Name Packing Batch Qty Free Rate Value"     (rows led by Bill No e.g. SAPnnnnn; '-' value => 0)
      C "DATE TRN.NO. CODE ITEM NAME QTY. FREE RATE VALUE"                      (party from 'CUSTOMER :' heading; optional date/trn prefix)
      D "Name Pack Bill Ref Date MRP Batch Qty Free Rate Amount"               (party = comma-prefixed line; 'Party Total =>')
    """
    headers = ["Party Name", "Product Name", "Inv No", "Date", "Qty", "Free", "Rate", "Amount"]
    raw_lines = text.splitlines()
    lines = [_despace(l).strip() for l in raw_lines]
    low = "\n".join(lines[:8]).lower()

    if "trn.no" in low and "item name" in low:
        layout = "C"
    elif "bill ref" in low and "mrp" in low:
        layout = "D"
    elif re.search(r"bill\s*no\.?\s*bill", low) or ("bill no." in low and "batch" in low and "value" in low):
        layout = "B"
    else:
        layout = "A"

    rows = []
    party = None

    def is_noise(s):
        u = s.upper()
        if not s:
            return True
        if set(s) <= set("- "):
            return True
        if u.startswith("PAGE ") or u.startswith("PAGE NO") or u.startswith("CONT"):
            return True
        if u.startswith("FROM :") or u.startswith("FORM:") or u.startswith("NORMAL FROM"):
            return True
        return False

    def is_mfg(s):
        return s.upper().replace(' ', '').startswith("KLM")

    def _recover_qfr_a(s, amt, nums, raw=None):
        """Layout A: recover (qty, free, rate) from the run after the bill date.

        Plain rows keep their integer tokens ("... 11/05/26 4 0 82.16 322.08").
        Letter-spaced rows glue the whole run into one digit blob after _despace
        ("3 0 1 2 9 . 0 0 3 7 9 . 2 7" -> "30129.00379.27"): peel the trailing
        Amount, then split the remainder into <qty><free><rate> by testing every
        split against qty*rate ~= amount (invoices discount up to ~6%). Returns
        blanks when no split is confident — exactly the previous behaviour.
        """
        # Plain rows: _despace glues the two single-digit columns Qty+F.Qty
        # ("4 0" -> "40"), so the space-separated `mp` path below fails and the
        # glued path can only recover the split when qty*rate ~= amount. A
        # DISCOUNTED row (amount far below qty*rate, e.g. "4 0 112.51 220.51")
        # then loses qty/rate. Read the tail off the RAW (non-despaced) line
        # where the digits are still separated — same trick layout C uses. Gated
        # to the clean 2-decimal (Rate, Amount) shape: require the tail's Value to
        # equal our amount, so a 3-decimal (Rate Amount Value) row can't misread
        # Amount as Rate; letter-spaced rows fail this (their decimals carry
        # spaces) and fall through to the glued path unchanged.
        if raw is not None:
            mt = _TAIL_C.search(raw.strip())
            if mt:
                try:
                    if abs(float(mt.group("val").replace(",", "")) - amt) < 0.005:
                        fr = mt.group("free")
                        return (
                            mt.group("qty"),
                            "0" if fr == "-" else str(int(fr)),
                            "%.2f" % float(mt.group("rate").replace(",", "")),
                        )
                except ValueError:
                    pass
        md = re.search(r"\d{2}/\d{2}/\d{2}", s)
        if not md:
            return "", "", ""
        seg = s[md.end():]
        mp = re.match(r"\s+(\d+)\s+(\d+)\s+(-?[\d,]+\.\d{2})\s", seg + " ")
        if mp:
            return mp.group(1), mp.group(2), mp.group(3).replace(",", "")
        # glued path: cut off the intact trailing Value token, digits-only blob
        mfin = list(NUM.finditer(seg))
        if len(mfin) < 2:
            return "", "", ""
        blob = re.sub(r"[^0-9.]", "", seg[: mfin[-1].start()])
        a = "%.2f" % amt
        if blob.endswith(a) and len(blob) > len(a):
            blob = blob[: -len(a)]
        best = None
        for cut in range(1, min(6, len(blob))):
            rate_s = blob[-(cut + 3):]
            if not re.fullmatch(r"\d{1,5}\.\d{2}", rate_s):
                continue
            qf = blob[: -(cut + 3)]
            if not qf.isdigit() or not qf:
                continue
            for i in range(1, len(qf) + 1):
                qty_s, free_s = qf[:i], qf[i:] or "0"
                qty_v, rate_v = int(qty_s), float(rate_s)
                if qty_v < 1 or rate_v <= 0:
                    continue
                if int(free_s) > qty_v * 5 + 10:
                    continue
                err = abs(qty_v * rate_v - amt) / max(amt, 0.01)
                if err <= 0.10 and (best is None or err < best[0]):
                    best = (err, qty_s, str(int(free_s)), rate_s)
        if best:
            return best[1], best[2], best[3]
        return "", "", ""

    if layout == "A":
        for _i, s in enumerate(lines):
            if is_noise(s):
                continue
            if s.startswith("Mfg.Total") or s.startswith("Total Value") or s.startswith("Product Name"):
                continue
            if "VIVEK MEDICAL" in s.upper() or "BASEMENT" in s.upper():
                continue
            nums = NUM.findall(s)
            has_ref = re.search(r"[A-Z]/\d", s) and re.search(r"\d{2}/\d{2}/\d{2}", s)
            if has_ref and nums:
                if not party:
                    continue
                amt = float(nums[-2].replace(',', '')) if len(nums) >= 3 else float(nums[-1].replace(',', ''))
                mref = re.search(r"([A-Z]/\d+)", s)
                prod = s[:mref.start()].strip() if mref else NUM.split(s)[0].strip()
                mi = re.search(r"([A-Z]/\s*\d+|M/\s*\d+)", s)
                inv = mi.group(1).replace(' ', '') if mi else ""
                md = re.search(r"\d{2}/\d{2}/\d{2}", s)
                qty, free, rate = _recover_qfr_a(s, amt, nums, raw_lines[_i])
                rows.append([party, prod, inv, md.group(0) if md else "",
                             qty, free, rate, "%.2f" % amt])
            elif not is_mfg(s) and not nums:
                party = s
        return headers, rows

    if layout == "B":
        for s in lines:
            if is_noise(s):
                continue
            su = s.upper()
            if (s.startswith("Total for") or s.startswith("Grand Total") or s.startswith("***")
                    or "SWASTIK AGENCIES" in su or "GULMANDI" in su
                    or "CHAMPAVATI" in su or "GAJANAN" in su or "ITEMWISE-BILLWISE" in su
                    or s.startswith("Bill No.") or s == "Date"):
                continue
            # Bill No. may be a 3-letter-prefixed code (PDA/DIS/SAP/RMC + 5 digits)
            # OR a single-letter-prefixed code (RAAJYOG's "R" + 7 digits, e.g.
            # R2601439). The old {2,4}-letter/{4,6}-digit gate dropped every "R#######"
            # line, keeping only the rare RMC* bills -> mass under-extraction. Widen the
            # prefix to 1-4 letters and 4-7 digits; the mandatory "\d{2}/\d{2}" bill-date
            # anchor after it keeps party headings (no digits+slash) out.
            m = re.match(r"^([A-Z]{1,4}\d{4,7})\s+(\d{2}/\d{2})\s+(.*)$", s)
            if m:
                inv, dt, rest = m.group(1), m.group(2), m.group(3)
                nums = NUM.findall(rest)
                if rest.rstrip().endswith("-") and nums:
                    val = 0.0
                else:
                    val = float(nums[-1].replace(',', '')) if nums else 0.0
                prod = NUM.split(rest)[0]
                prod = re.sub(r"\s+[A-Z0-9]+\s*$", "", prod).strip()
                # Value column IS Qty x Rate: rate = 2nd-last decimal, qty derived
                # (the qty/free integers carry no decimal so NUM can't read them).
                # Only fill qty on a clean integer quotient (never fabricate).
                rate = qty = free = ""
                if len(nums) >= 2:
                    rr = float(nums[-2].replace(",", ""))
                    if rr > 0:
                        rate = "%.2f" % rr
                        q = val / rr
                        qr = round(q)
                        if qr >= 0 and abs(q - qr) <= 0.02:
                            qty = str(qr)
                # Free column: the integer Qty/Free tokens sit between Batch and
                # Rate (NUM can't read them: no decimals), and _despace glues
                # single-digit pairs into one 2-char token ("9 2"->"92"; free-only
                # rows print Value '-' and glue "0 2"->"02"). Recover free ONLY
                # when the trailing digit token(s) before the rate unambiguously
                # agree with the derived qty (two tokens led by qty, or the 2-char
                # single-digit glue); otherwise leave "" exactly as before.
                is_dash = rest.rstrip().endswith("-") and bool(nums)
                mn = list(NUM.finditer(rest))
                if mn and (is_dash or qty):
                    pos = mn[-1].start() if is_dash else mn[-2].start()
                    dig = []
                    for t in reversed(rest[:pos].split()):
                        if t.isdigit() and len(dig) < 2:
                            dig.append(t)
                        else:
                            break
                    dig.reverse()
                    if dig and is_dash:
                        if len(dig) == 2 and dig[0] == "0":
                            free = str(int(dig[1]))
                        elif len(dig[-1]) == 2 and dig[-1][0] == "0":
                            free = dig[-1][1]
                    elif dig and qty:
                        if len(dig) == 2 and dig[0] == qty:
                            free = str(int(dig[1]))
                        elif len(qty) == 1 and len(dig[-1]) == 2 and dig[-1][0] == qty:
                            free = dig[-1][1]
                rows.append([party, prod, inv, dt, qty, free, rate, "%.2f" % val])
            else:
                nums = NUM.findall(s)
                if not nums and not _is_continuation(s):
                    party = s
        return headers, rows

    if layout == "C":
        for _idx, s in enumerate(lines):
            if is_noise(s):
                continue
            if s.startswith("CUSTOMER"):
                m = re.search(r"CUSTOMER\s*:\s*(.*)", s)
                if m:
                    name = m.group(1).strip()
                    name = re.sub(r"^\d+[A-Z]?\d*\s+", "", name)
                    name = re.sub(r"\s+\d+$", "", name)
                    party = name.strip()
                continue
            if s.startswith("GRAND") or s.startswith("DATE ") or s.startswith("COMPANY") or s.startswith("ITEM-BILL") or s.startswith("CUSTOMER TOTAL") or "SANTOSH ENTER" in s.upper() or "KESHO RAM" in s.upper():
                continue
            nums = NUM.findall(s)
            if len(nums) >= 2:
                val = float(nums[-1].replace(',', ''))
                md = re.match(r"^(\d{1,2}-[A-Za-z]{3}-\d{2})\s+(\S+)\s+(.*)$", s)
                if md:
                    dt, inv, rest = md.group(1), md.group(2), md.group(3)
                else:
                    dt, inv, rest = "", "", s
                prod = re.split(r"\s+-?\d", rest)[0].strip()
                # Recover integer Qty / '-'|int Free / Rate that the decimal-only
                # NUM regex misses. Tail-anchored on the RAW (non-despaced) line,
                # because _despace glues the single-digit Qty/Free pair ("5 1"
                # -> "51"). Falls back to blanks (prior behaviour) when the row
                # does not end in the expected shape.
                qty = free = rate = ""
                mt = _TAIL_C.search(raw_lines[_idx].strip())
                if mt:
                    qty = mt.group("qty")
                    free = "0" if mt.group("free") == "-" else str(int(mt.group("free")))
                    rate = "%.2f" % float(mt.group("rate").replace(",", ""))
                rows.append([party, prod, inv, dt, qty, free, rate, "%.2f" % val])
        return headers, rows

    if layout == "D":
        for s in lines:
            if is_noise(s):
                continue
            if s.startswith("Party Total") or s.startswith("Grand Total") or s.startswith("Name Pack") or "PATEL MEDICAL AGENC" in s.upper() or "KOTHARI" in s.upper() or s.startswith("Mob"):
                continue
            nums = NUM.findall(s)
            md = re.search(r"\d{2}-\d{2}-\d{4}", s)
            if md and len(nums) >= 2:
                amt = float(nums[-1].replace(',', ''))
                prod = re.split(r"\s+[A-Z0-9]+[-/]", s)[0].strip()
                mi = re.search(r"([A-Z]{1,3}-?[A-Z]?/\d+)", s)
                rows.append([party, prod, mi.group(1) if mi else "", md.group(0), "", "", "", "%.2f" % amt])
            elif "," in s and not nums:
                party = s.split(',')[0].strip()
        return headers, rows

    return headers, rows