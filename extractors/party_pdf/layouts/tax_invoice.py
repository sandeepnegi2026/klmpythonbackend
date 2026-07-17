import io
import re


def _flat_rows(text):
    """Original flat text-regex parse. Returns (party, [ [product, qty, rate, amount], ... ])
    in printed order. A glyph-garbled line fails the row regex and is skipped."""
    party = ""
    out = []
    ROW = re.compile(
        r"^(\d{6,8})\s+(.+?)\s+(\d{1,2}/\d{2})\s+(\d+)\s+([\d.]+)\s+"
        r"([\d.]+)\s+([\d.]+)\s+(\d+)%\s+([\d.]+)$"
    )
    for raw in text.split("\n"):
        s = re.sub(r"\s+", " ", raw.strip())
        if not s:
            continue
        if not party:
            mb = re.search(r"To Buyer Name\s*:\s*(.+)$", s)
            if mb:
                party = mb.group(1).strip()
                continue
        m = ROW.match(s)
        if m and party:
            out.append({
                "product": m.group(2).strip(),
                "qty": m.group(4),
                "rate": m.group(6),
                "amount": m.group(9),
            })
    return party, out


def _num(s):
    return re.sub(r"[^\d.]", "", s or "")


def _pick(block, xanchor, tol):
    """Nearest numeric word to xanchor (skips pct tokens)."""
    cands = []
    for w in block:
        if abs(w["x0"] - xanchor) <= tol and re.search(r"\d", w["text"]) \
           and not w["text"].endswith("%"):
            cands.append(w)
    if not cands:
        return None
    cands.sort(key=lambda w: abs(w["x0"] - xanchor))
    return cands[0]["text"]


def _positional_blocks(file_bytes):
    """Per-item positional records anchored on the column header + successive HSN
    codes (leftmost column). Recovers glyph-interleaved item lines the flat regex
    drops. Returns list of dicts {amount, qty, rate, name, top} in printed order,
    or [] if the page shape is not the expected single-buyer invoice grid."""
    import pdfplumber

    recs = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
            if not words:
                continue
            # column header row: carries Amount + a Qty. + Rate token on one band
            hdr = None
            for w in words:
                if w["text"] != "Amount":
                    continue
                band = [x for x in words if abs(x["top"] - w["top"]) <= 3]
                txts = {t["text"] for t in band}
                if any(t.startswith("Qty") for t in txts) and "Rate" in txts:
                    hdr = band
                    break
            if hdr is None:
                continue
            col = {t["text"].rstrip("."): t["x0"] for t in hdr}
            x_qty, x_rate, x_amt = col.get("Qty"), col.get("Rate"), col.get("Amount")
            x_hsn = col.get("HSN.C", 22)
            if x_qty is None or x_rate is None or x_amt is None:
                continue
            hdr_top = hdr[0]["top"]

            data = [w for w in words if w["top"] > hdr_top + 2]
            # cut at the CLASS/FLASH tax-summary footer (leftmost column)
            cut = None
            for w in sorted(data, key=lambda w: w["top"]):
                if w["text"] in ("FLASH", "CLASS") and w["x0"] < 60:
                    cut = w["top"]
                    break
            if cut is not None:
                data = [w for w in data if w["top"] < cut - 1]

            hsn_lines = sorted(
                (w for w in data
                 if abs(w["x0"] - x_hsn) < 15 and re.fullmatch(r"\d{6,8}", w["text"])),
                key=lambda w: w["top"],
            )
            if not hsn_lines:
                continue
            bounds = [w["top"] for w in hsn_lines] + [float("inf")]
            for i in range(len(hsn_lines)):
                lo, hi = bounds[i] - 3, bounds[i + 1] - 3
                block = [w for w in data if lo <= w["top"] < hi]
                amt = _pick(block, x_amt, tol=18)
                if amt is None:
                    continue
                qty = _pick(block, x_qty, tol=14)
                rate = _pick(block, x_rate, tol=12)
                name_toks = [
                    w for w in block
                    if w["x0"] < x_qty - 20 and not re.fullmatch(r"\d{6,8}", w["text"])
                ]
                name_toks.sort(key=lambda w: (round(w["top"]), w["x0"]))
                name = re.sub(r"\s+", " ",
                              " ".join(t["text"] for t in name_toks)).strip()
                recs.append({
                    "amount": _num(amt),
                    "qty": _num(qty) if qty else "",
                    "rate": _num(rate) if rate else "",
                    "name": name,
                    "top": hsn_lines[i]["top"] + page.page_number * 100000,
                })
    return recs


def parse_tax_invoice(text, file_bytes=None):
    """Single-buyer tax invoice (MARG ERP NANO style). One 'To Buyer Name : X'
    header names the party; each line item is
    '<HSN> <product ... pack mfr batch> <exp> <qty> <mrp> <rate> <disc%> <gst%> <amount>'.
    The buyer becomes the Party Name on every line.

    A minority of item lines arrive glyph-interleaved (two physical print rows
    merged with scrambled character order), so the flat row regex rejects them and
    the item is silently dropped (E1). When the raw PDF bytes are available we run a
    positional pass keyed on the fixed column x-anchors (HSN / Qty / Rate / Amount)
    and splice in any item whose Amount the flat parser missed, preserving printed
    order. Every item the flat parser already reads is emitted byte-for-byte
    unchanged (its clean name wins); only the dropped glyph rows are recovered.
    """
    H = ["Party Name", "Product Name", "Qty", "Rate", "Amount"]
    party, flat = _flat_rows(text)

    if not file_bytes:
        return H, [[party, r["product"], r["qty"], r["rate"], r["amount"]] for r in flat]

    try:
        recs = _positional_blocks(file_bytes)
    except Exception:
        recs = []

    # If positional recovery found no extra items (or failed), keep flat output
    # byte-identical.
    flat_amts = {}
    for idx, r in enumerate(flat):
        flat_amts.setdefault(_num(r["amount"]), []).append(idx)

    extra = [rec for rec in recs if rec["amount"] not in flat_amts]
    if not extra or len(recs) <= len(flat):
        return H, [[party, r["product"], r["qty"], r["rate"], r["amount"]] for r in flat]

    # Merge: walk positional records in printed order; for an amount the flat
    # parser already produced use the flat (clean) name, else use the positional
    # (best-effort) name. This inserts recovered glyph rows in their true position
    # while leaving all flat rows unchanged.
    used = set()
    merged = []
    for rec in sorted(recs, key=lambda r: r["top"]):
        a = rec["amount"]
        idxs = [i for i in flat_amts.get(a, []) if i not in used]
        if idxs:
            i = idxs[0]
            used.add(i)
            fr = flat[i]
            merged.append([party, fr["product"], fr["qty"], fr["rate"], fr["amount"]])
        else:
            merged.append([party, rec["name"], rec["qty"], rec["rate"], rec["amount"]])
    # Safety: never drop a flat row that positional somehow missed.
    for i, fr in enumerate(flat):
        if i not in used:
            merged.append([party, fr["product"], fr["qty"], fr["rate"], fr["amount"]])
    return H, merged
