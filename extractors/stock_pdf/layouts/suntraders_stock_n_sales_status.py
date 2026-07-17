"""SUN TRADERS "Stock n Sales Status" — Data Spec (www.dsgst.in) browser/app
print export.

Masthead:
    SUN TRADER
    GSTIn:22...
    Shop 1,Medical Complex,...
    Page 1
    Stock n Sales Status - '01-Jun-2026' to '30-Jun-2026'
    Item Pkg Last Pur. Op Qty In Qty Out Qty Cl Qty
                       Rate
    <DIV BAND e.g. KLM-COSMO>
    1 EKRAN -30 SILICON  30 GM   277.63  30  2  28
    ...
    KLM-COSMO Total 18 items 45991.76 25560.39 21657.13 50301.7

Column layout (5 numeric columns, all RIGHT-ALIGNED, blank when zero):

    Item(name)  Pkg   Last Pur.Rate | Op Qty | In Qty | Out Qty | Cl Qty

Every data line starts with a running serial number, then the item name, an
optional pack, the Last Purchase Rate (a `dd.dd` decimal) and up to four qty
integers.  Because the qty cells are right-aligned and print BLANK (not '0')
when zero, a flat token-count parser mis-binds them (a row that carries only
In+Out+Cl looks like Op+In+Out) and the coarse `n_rects>400 -> marg_bordered`
geometric parser drops ~75% of the rows outright (42 of 166 kept, GREEN-but-
incomplete).  We therefore parse POSITIONALLY: read the header row's Op/In/Out/Cl
word x-positions to derive four column bands, then bin each data row's numeric
words into those bands by x-centre.  This self-calibrates per page and is immune
to blank interior cells.

Reconcile identity (Data Spec):  Cl = Op + In - Out
  -> In  Qty -> purchase_stock   (inflow)
     Out Qty -> sales_qty        (outflow)
     Op / Cl -> opening / closing_stock
The band-Total rows ("<DIV> Total N items ...") and the grand "Total 166 items"
line start with a division word (letters), not a serial, so they never match the
`^<serial>` data-line pattern.  Zero-stock catalog rows print as
"<serial> <NAME> -" (a lone trailing dash, no rate/qty) and are kept with all
qtys 0 for completeness.
"""
import io
import re

_RATE_RE = re.compile(r"^\d[\d,]*\.\d\d$")          # Last Pur.Rate: 277.63
_INT_RE = re.compile(r"^-?\d[\d,]*$")               # qty integers (may be neg.)
_SERIAL_RE = re.compile(r"^\d+$")


def _to_i(t):
    try:
        return int(round(float(t.replace(",", ""))))
    except ValueError:
        return 0


def _to_f(t):
    try:
        return float(t.replace(",", ""))
    except ValueError:
        return 0.0


def _header_bands(words):
    """From the 'Op Qty In Qty Out Qty Cl Qty' header, return the four right-edge
    x1 anchors for Op/In/Out/Cl (top-most occurrence)."""
    anchor = {}
    for w in sorted(words, key=lambda w: w["top"]):
        t = w["text"]
        if t in ("Op", "In", "Out", "Cl") and t not in anchor:
            # header band sits in the top ~130px; ignore stray body matches
            if w["top"] < 140:
                anchor[t] = w["x1"]
        if len(anchor) == 4:
            break
    if len(anchor) != 4:
        return None
    # Right-aligned qty VALUES land ~40-55px to the right of the label's x1.
    # Build band centres midway between consecutive label anchors; a value word
    # is assigned to the band whose centre its own x1 (right edge) is nearest.
    return anchor  # {'Op':x1,'In':x1,'Out':x1,'Cl':x1}


def _assign(nums, anchor):
    """Assign numeric words (each dict with x1) to Op/In/Out/Cl by nearest label
    anchor. Values right-align ~40-55px right of their label; using label x1 as
    the reference and nearest-neighbour is robust to that constant offset."""
    order = ["Op", "In", "Out", "Cl"]
    xs = [anchor[k] for k in order]
    out = {"Op": 0, "In": 0, "Out": 0, "Cl": 0}
    for w in nums:
        # value right edge; snap to nearest label anchor
        best = min(range(4), key=lambda i: abs(w["x1"] - xs[i]))
        out[order[best]] = _to_i(w["text"])
    return out


def parse_suntraders_stock_n_sales_status(text, file_bytes=None):
    if not file_bytes:
        return []
    import pdfplumber

    records = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            words = page.extract_words(x_tolerance=1.5)
            anchor = _header_bands(words)
            if not anchor:
                continue
            # cluster words into visual rows by rounded top
            by_top = {}
            for w in words:
                by_top.setdefault(round(w["top"]), []).append(w)
            for top in sorted(by_top):
                rw = sorted(by_top[top], key=lambda w: w["x0"])
                if not rw:
                    continue
                # data rows begin with a bare serial number at the left margin
                first = rw[0]
                if first["x0"] > 90 or not _SERIAL_RE.match(first["text"]):
                    continue
                body = rw[1:]
                if not body:
                    continue
                # a real item line has letters in its name head
                if not any(re.search(r"[A-Za-z]", w["text"]) for w in body):
                    continue

                # locate the Last Pur.Rate word (dd.dd) — the anchor between the
                # name/pack head and the qty tail
                rate_idx = None
                for i, w in enumerate(body):
                    if _RATE_RE.match(w["text"].replace(",", "")):
                        rate_idx = i
                        break
                if rate_idx is None:
                    # zero-stock row: "<serial> <NAME ...> -"  (no rate, no qty)
                    name_toks = [w["text"] for w in body if w["text"] != "-"]
                    name = " ".join(name_toks).strip()
                    if not name:
                        continue
                    records.append({
                        "product_name": name,
                        "opening_stock": 0,
                        "purchase_stock": 0,
                        "sales_qty": 0,
                        "closing_stock": 0,
                    })
                    continue

                head = body[:rate_idx]
                rate = _to_f(body[rate_idx]["text"])
                tail = [w for w in body[rate_idx + 1:] if _INT_RE.match(w["text"].replace(",", ""))]

                # name/pack: everything left of the rate. Pack column starts
                # ~x0 250 (Pkg header). Split name vs pack on x0.
                name_toks = [w["text"] for w in head if w["x0"] < 245]
                pack_toks = [w["text"] for w in head if w["x0"] >= 245]
                name = " ".join(name_toks).strip()
                if not name:
                    continue

                b = _assign(tail, anchor)
                rec = {
                    "product_name": name,
                    "opening_stock": b["Op"],
                    "purchase_stock": b["In"],   # In Qty  (inflow)
                    "sales_qty": b["Out"],        # Out Qty (outflow)
                    "closing_stock": b["Cl"],
                    "rate": rate,
                }
                if pack_toks:
                    rec["pack"] = " ".join(pack_toks).strip()
                records.append(rec)
    return records
