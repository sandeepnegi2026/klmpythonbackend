import io
import re

# ---------------------------------------------------------------------------
# DEEPAA AGENCIES, ERODE (KLM division reports) party layout:
#   "PARTY WISE SALES STATEMENT"
#
# Title / furniture (repeated every page):
#   "_M _DEEPAA AGENCIES, ERODE_" | "PARTY WISE SALES STATEMENT FOR THE PERIOD
#   01/05/2026 TO 31/05/2026 PAGE: N" | division band "KLM - (COSMO Q)" |
#   dashed rule | column header "PARTY NAME ITEM NAME REP FRE QTY VALUE DISC
#   NET AMT" | dashed rule | body ... | per-division "COMPANY TOTAL=>".
#
# Two reference files exist and they use DIFFERENT page geometries, so the
# parser is POSITIONAL and derives every column x-anchor from the header row(s)
# per page, then supports both an INLINE and a WRAPPED layout:
#
#   * MAY AREAWISE DEEPAA.pdf  (page width 612, INLINE):
#       header on ONE line; a product row is a single baseline:
#         <PARTY NAME x0<item_x> <ITEM+PACK> <QTY> <VALUE> <DISC> <NET AMT>
#       e.g. "SRI SARAVANA MEDICALS, COSMOQ BRIGHT.SERUM. 30ML 2 683.38 28.48 711.86"
#
#   * KLM - ALL _7 files merged_.pdf  (page width 595, WRAPPED):
#       header spans TWO lines ("...QTY" then "VALUE DISC NET AMT"); a product
#       row spans TWO baselines: line A = <PARTY NAME <ITEM+PACK> <QTY>>, the
#       immediately following line B = <VALUE DISC NET AMT> floats (no item).
#       TOTAL=> likewise: "<LOCATION> TOTAL=>" then the block net on the next line.
#
# In both files the row semantics are identical:
#   PARTY NAME = name band (x0 < item_x) of the FIRST product line of a block,
#     carried down onto continuation product lines (whose name band is ADDRESS)
#     until the block-closing "<LOCATION> TOTAL=>" line.
#   PARTY LOCATION = the first name-band token on the TOTAL=> line (the town).
#   PRODUCT NAME = item band (x0 >= item_x) text (company code + name + pack).
#   FRE column is never populated -> free_qty = 0. RATE is not printed.
#   AMOUNT = NET AMT (net of discount) -> reconciles to the printed per-division
#     "COMPANY TOTAL=>" NET-AMT column (COSMO 83106.16, COSMOCOR 87128.07,
#     DERMA 136539.40, ...; grand net 547960.82; grand qty 2984).
#
# When the party name is long the last name token GLUES the item's leading
# company code across the item boundary (e.g. "BUSSTAND)COSMOQ",
# ":M.B.B.S.,D.DCOSMOQ"); such a straddling token (x0<item_x and x1>item_x) is
# split by character-width at item_x so the name and item bands each get their
# correct half.
# ---------------------------------------------------------------------------

H = ["Party Name", "Location", "Product Name", "Pack", "Free", "Qty", "Amount"]

_INT = re.compile(r"^-?\d+$")
_DEC = re.compile(r"^-?[\d,]*\.\d+$")
_TOTAL = "TOTAL=>"


def _num(t):
    try:
        return float(str(t).replace(",", ""))
    except (ValueError, AttributeError, TypeError):
        return 0.0


def _split_at_x(w, boundary):
    """Split one word at pixel ``boundary`` by character width -> (left, right)."""
    text = w["text"]
    x0, x1 = w["x0"], w["x1"]
    if x1 <= boundary:
        return text, ""
    if x0 >= boundary:
        return "", text
    span = x1 - x0
    if span <= 0 or not text:
        return text, ""
    idx = int(round((boundary - x0) / span * len(text)))
    idx = max(0, min(len(text), idx))
    return text[:idx], text[idx:]


def _bands(ws, item_x, qty_hi):
    """Split a line's words into (name_band tokens, item_band tokens), ungluing
    the single token that may straddle item_x. Only words left of qty_hi count
    (numeric columns are excluded)."""
    name, item = [], []
    for w in ws:
        if w["x0"] >= qty_hi:
            continue
        if w["x1"] <= item_x:
            if w["text"]:
                name.append(w["text"])
        elif w["x0"] >= item_x:
            if w["text"]:
                item.append(w["text"])
        else:
            left, right = _split_at_x(w, item_x)
            if left:
                name.append(left)
            if right:
                item.append(right)
    return name, item


def _find_header(lines_sorted):
    """Locate the 'PARTY NAME ITEM NAME REP FRE QTY [VALUE DISC NET AMT]' header
    and return the column anchors: (item_x, qty_lo, qty_hi, fre_lo, fre_hi,
    net_lo, net_hi, wrapped). Returns None if not found on this page."""
    tops = sorted(lines_sorted)
    for i, y in enumerate(tops):
        ws = lines_sorted[y]
        texts = {w["text"].upper(): w for w in ws}
        if "PARTY" in texts and "ITEM" in texts and "QTY" in texts:
            item_x = texts["ITEM"]["x0"] - 2.0
            qx = texts["QTY"]
            qty_lo, qty_hi = qx["x0"] - 8.0, qx["x1"] + 12.0
            fre_lo = fre_hi = None
            if "FRE" in texts:
                fx = texts["FRE"]
                fre_lo, fre_hi = fx["x0"] - 6.0, fx["x1"] + 4.0
            # NET / AMT may be on the SAME header line (inline) or the NEXT one
            # (wrapped). Search this line first, then the following line.
            net_lo = net_hi = None
            wrapped = False
            if "NET" in texts and "AMT" in texts:
                net_lo = texts["NET"]["x0"] - 6.0
                net_hi = texts["AMT"]["x1"] + 12.0
            elif i + 1 < len(tops):
                ws2 = lines_sorted[tops[i + 1]]
                t2 = {w["text"].upper(): w for w in ws2}
                if "NET" in t2 and "AMT" in t2:
                    net_lo = t2["NET"]["x0"] - 6.0
                    net_hi = t2["AMT"]["x1"] + 12.0
                    wrapped = True
            if net_lo is None:
                continue
            return (item_x, qty_lo, qty_hi, fre_lo, fre_hi, net_lo, net_hi,
                    wrapped)
    return None


def _qty_tok(ws, qty_lo, qty_hi):
    for w in ws:
        if qty_lo <= w["x0"] < qty_hi and _INT.match(w["text"]):
            return w["text"]
    return None


def _fre_tok(ws, fre_lo, fre_hi):
    if fre_lo is None:
        return None
    for w in ws:
        if fre_lo <= w["x0"] < fre_hi and _INT.match(w["text"]):
            return w["text"]
    return None


def _net_from_floats(ws, net_lo, net_hi):
    """NET AMT is the rightmost float at/after net_lo (VALUE, DISC precede it)."""
    best = None
    for w in ws:
        if w["x0"] >= net_lo and _DEC.match(w["text"]):
            if best is None or w["x0"] > best["x0"]:
                best = w
    return best["text"] if best else None


def _is_furniture(joined):
    low = joined.lower()
    return (joined.startswith("---")
            or "party wise sales statement" in low
            or joined.startswith("PARTY NAME")
            or "page:" in low
            or joined.startswith("KLM -")
            or "deepaa agencies" in low
            or joined.startswith("_M")
            or "item name rep fre" in low
            or joined.strip() in ("VALUE DISC NET AMT",))


def _loc_from_total(ws, item_x):
    for w in ws:
        if w["x0"] < item_x and _TOTAL not in w["text"] \
                and not _DEC.match(w["text"]) and not _INT.match(w["text"]):
            return w["text"].rstrip(",").strip()
    return ""


def parse_klm_party_wise_statement(text, file_bytes=None):
    if not file_bytes:
        return H, []

    import pdfplumber

    rows = []

    def close_block(state, loc):
        if state["party"] and loc:
            for r in reversed(rows):
                if r[0] != state["party"]:
                    break
                if not r[1]:
                    r[1] = loc
        state["party"] = ""
        state["open"] = False
        state["first"] = True

    # Flatten every page into ONE continuous stream of visual lines. Continuation
    # pages in the wrapped export repeat NO header, so the header (and its column
    # anchors) is derived once from the first page that carries it and applied to
    # the whole file. Party blocks are delimited by TOTAL=> / COMPANY TOTAL=>,
    # never by page breaks, so a single linear pass is correct.
    hdr = None
    stream = []  # list of (sorted words) per visual line, in reading order
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            if not words:
                continue
            lines = {}
            for w in words:
                lines.setdefault(round(w["top"]), []).append(w)
            for y in lines:
                lines[y].sort(key=lambda w: w["x0"])
            if hdr is None:
                hdr = _find_header(lines)
            for y in sorted(lines):
                stream.append(lines[y])

    if hdr is None:
        return H, []
    item_x, qty_lo, qty_hi, fre_lo, fre_hi, net_lo, net_hi, wrapped = hdr

    state = {"party": "", "open": False, "first": True}
    j = 0
    n = len(stream)
    while j < n:
        ws = stream[j]
        joined = " ".join(w["text"] for w in ws)

        if "COMPANY" in joined and _TOTAL in joined:
            close_block(state, "")   # discard any dangling town
            state["party"] = ""
            j += 1
            continue

        if _TOTAL in joined:
            loc = _loc_from_total(ws, item_x)
            close_block(state, loc)
            j += 1
            continue

        if _is_furniture(joined):
            j += 1
            continue

        qtok = _qty_tok(ws, qty_lo, qty_hi)
        if qtok is None:
            j += 1
            continue

        # ---- product row: qty present. Get NET AMT (inline or wrapped) -------
        if wrapped:
            net = None
            if j + 1 < n:
                ws_next = stream[j + 1]
                if not any(w["x0"] >= item_x and not _DEC.match(w["text"])
                           and not _INT.match(w["text"]) for w in ws_next):
                    net = _net_from_floats(ws_next, net_lo, net_hi)
            if net is None:
                j += 1
                continue
            consume = 2
        else:
            net = _net_from_floats(ws, net_lo, net_hi)
            if net is None:
                j += 1
                continue
            consume = 1

        name_band, item_band = _bands(ws, item_x, qty_lo)

        if state["first"]:
            pname = " ".join(name_band).strip().rstrip(",").strip()
            if pname:
                state["party"] = pname
            state["first"] = False
            state["open"] = True

        product = " ".join(item_band).strip()
        fre = _fre_tok(ws, fre_lo, fre_hi)
        rows.append([
            state["party"], "", product, "",
            "%g" % (_num(fre) if fre else 0.0),
            "%g" % _num(qtok),
            "%.2f" % _num(net),
        ])
        j += consume

    return H, rows
