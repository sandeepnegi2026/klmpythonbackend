import re

# PROFITMAKER ("Customer & Product Analysis", Daxinsoft Technologies) party-wise
# customer/product export. The trailing numeric column set varies between exports
# (Qty Free Rate Value; +Mrp; or Mrp Rate PValue Gstper), so the parser reads each
# file's own column header row and maps tokens by that layout rather than assuming
# a fixed column count. Party (and optional Area) come from "Customer :" headings.

_DATE = re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4}$")
_CUST = re.compile(r"^Customer\s*:\s*(.+?)(?:\s+Area\s*:\s*(.+))?$")
# Some PROFITMAKER exports (S V PHARMA) prefix the division on the SAME band line:
# "Company :KLM COSMO Q DIVISION Customer :DR. M . AISWARYA". The _CUST regex is
# anchored at ^Customer so it never matches and every party stays blank. This gate
# fires ONLY when the line begins with "Company :" and carries "Customer :" after it.
_COMPANY_CUST = re.compile(
    r"^Company\s*:\s*(.+?)\s+Customer\s*:\s*(.+?)(?:\s+Area\s*:\s*(.+))?$")
_NUM_LEAD = re.compile(r"^-?[\d,]*\.?\d")

# normalized header token -> (canonical key, is_numeric_column)
_COLS = {
    "invno": ("invoice_number", False), "feedno": ("invoice_number", False),
    "billno": ("invoice_number", False),
    "date": ("invoice_date", False), "feeddate": ("invoice_date", False),
    "billdate": ("invoice_date", False),
    "product": ("product_name", False), "prodname": ("product_name", False),
    "productname": ("product_name", False),
    "pack": ("pack", False), "packing": ("pack", False),
    "batch": ("batch_no", False), "batchno": ("batch_no", False),
    "qty": ("qty", True), "free": ("free_qty", True),
    "mrp": ("mrp", True), "rate": ("rate", True),
    "value": ("amount", True), "pvalue": ("amount", True), "amount": ("amount", True),
    "gstper": ("gst_rate", True), "gst": ("gst_rate", True),
}
_DISPLAY = {
    "invoice_number": "Inv No", "invoice_date": "Date", "product_name": "Product Name",
    "pack": "Pack", "batch_no": "Batch", "qty": "Qty", "free_qty": "Free",
    "mrp": "Mrp", "rate": "Rate", "amount": "Value", "gst_rate": "Gst%",
}


def _norm(tok):
    return re.sub(r"[^a-z0-9]", "", tok.lower())


def _clean_num(tok):
    """Strip stray OCR letters/commas; return a numeric string or None. Keep a
    leading minus so sales-return rows retain their negative value ('-288.00');
    without it the sign is stripped and a return books as a positive sale. A clean
    positive token is byte-for-byte unchanged (sign='')."""
    body = tok.replace(",", "")
    sign = "-" if body.lstrip().startswith("-") else ""
    cleaned = re.sub(r"[^\d.]", "", body)
    try:
        float(cleaned)
        return sign + cleaned
    except ValueError:
        return None


def _read_header(lines):
    """Learn the layout from the column header row: (numeric canonicals, has_pack, has_batch)."""
    for line in lines:
        norms = [_norm(t) for t in line.split()]
        if "qty" in norms and "free" in norms:
            cols = [_COLS[n] for n in norms if n in _COLS]
            num_spec = [canon for canon, is_num in cols if is_num]
            has_pack = any(canon == "pack" for canon, _ in cols)
            has_batch = any(canon == "batch_no" for canon, _ in cols)
            return num_spec, has_pack, has_batch
    return [], False, False


def _rescue_watermark_tail(toks, n):
    """Repair a detail line whose numeric tail is corrupted by a single stray
    watermark glyph. PROFITMAKER can print the vendor name as a faint diagonal
    watermark; pdfminer occasionally drops one of its letters into a text line,
    either as a standalone token ('... 0.00 l 288.00 420.00 288.00') or glued
    onto the front of a number ('s10.00'). Called ONLY for lines that already
    FAILED the strict numeric-tail check (previously dropped outright), and
    repairs at most ONE glyph, so every line the strict path accepts is
    untouched. Returns the repaired token list, or None to keep the old skip."""
    out, repairs, got = [], 0, 0
    for tok in reversed(toks):
        if got < n:
            if _NUM_LEAD.match(tok):
                out.append(tok)
                got += 1
            elif len(tok) == 1 and tok.isalpha() and repairs == 0:
                repairs += 1  # stray standalone glyph inside the tail: drop it
            elif (len(tok) > 1 and tok[0].isalpha() and repairs == 0
                  and _NUM_LEAD.match(tok[1:])):
                out.append(tok[1:])  # glyph glued onto a number: strip it
                got += 1
                repairs += 1
            else:
                return None
        else:
            out.append(tok)
    if got < n or repairs != 1:
        return None
    return out[::-1]


def parse_profitmaker(text):
    lines = text.split("\n")
    num_spec, has_pack, has_batch = _read_header(lines)
    if "qty" not in num_spec:
        return [], []
    H = ["Party Name", "Area", "Inv No", "Date", "Product Name", "Pack", "Batch"] + \
        [_DISPLAY[c] for c in num_spec]
    n = len(num_spec)
    rows, party, area = [], "", ""
    for raw in lines:
        s = raw.strip()
        if not s:
            continue
        cust = _CUST.match(s)
        if cust:
            party = cust.group(1).strip()
            area = (cust.group(2) or "").strip()
            continue
        combo = _COMPANY_CUST.match(s)
        if combo:
            party = combo.group(2).strip()
            area = (combo.group(3) or "").strip()
            continue
        if s.startswith(("Total", "Grand Total", "From ", "Page", "Inv.No", "FeedNo")):
            continue
        toks = s.split()
        if len(toks) < 3 + n or not _DATE.match(toks[1]):
            continue
        tail = toks[-n:]
        if not all(_NUM_LEAD.match(t) for t in tail):
            repaired = _rescue_watermark_tail(toks, n)
            if repaired is None or len(repaired) < 3 + n:
                continue
            toks = repaired
            tail = toks[-n:]
        cleaned = [_clean_num(t) for t in tail]
        if any(c is None for c in cleaned):
            continue
        middle = toks[2:len(toks) - n]
        batch = middle.pop() if (has_batch and middle) else ""
        pack = middle.pop() if (has_pack and middle) else ""
        product = " ".join(middle).strip()
        if len(product) < 2:
            continue
        values = dict(zip(num_spec, cleaned))
        rows.append([party, area, toks[0], toks[1], product, pack, batch] +
                    [values[c] for c in num_spec])
    return H, rows
