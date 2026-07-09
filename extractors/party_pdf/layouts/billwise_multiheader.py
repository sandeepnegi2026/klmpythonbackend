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

# A wrapped product-name tail (dosage form) or a bare pack line is a data-row
# continuation, NOT a party heading. Used to stop such lines becoming fake
# parties (e.g. "NEVSOFT CLEANSING" wraps to "LOTION"; "100ML" pack tails).
_FORM_WORDS = {
    "LOTION", "LOTIO", "CREAM", "OINTMENT", "OINT", "GEL", "SHAMPOO", "SYRUP",
    "SOAP", "POWDER", "DROPS", "SOLUTION", "SUSPENSION", "TABLET", "TABLETS",
    "CAPSULE", "CAPSULES", "WASH", "SERUM", "SPRAY", "BAR", "KIT", "TONIC",
    "LIQUID", "SUNSCREEN", "FACE", "MOUTHWASH", "SCRUB", "MASK",
}
_PACK_LINE = re.compile(r"^\d+\s*(?:ML|GM|GMS|MG|G|TAB|TABS|CAP|CAPS|LTR|KG|GC|N|S)\.?$", re.I)


def _is_continuation(s):
    return bool(_PACK_LINE.match(s.strip())) or s.strip().rstrip(".").upper() in _FORM_WORDS

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

    if layout == "A":
        for s in lines:
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
                rows.append([party, prod, inv, md.group(0) if md else "", "", "", "", "%.2f" % amt])
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
            m = re.match(r"^([A-Z]{2,4}\d{4,6})\s+(\d{2}/\d{2})\s+(.*)$", s)
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
        for s in lines:
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
            if s.startswith("GRAND") or s.startswith("DATE ") or s.startswith("COMPANY") or s.startswith("ITEM-BILL") or "SANTOSH ENTER" in s.upper() or "KESHO RAM" in s.upper():
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
                rows.append([party, prod, inv, dt, "", "", "", "%.2f" % val])
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