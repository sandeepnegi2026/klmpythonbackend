"""Marg "Sales Analysis" party report — positional PDF parser (VENUS PHARMA / KLM).

Title:  "Sales Analysis  Date : 01-05-26 to 31-05-26"
Header:  Item | Qty | Free | Value # | Total Qty | Total Free | Total Value
         (#Value = Q*R [Sales])
3-level banding:
    Manufacturer band   "KLM LABORATORIES -COSMOCOR (XA0001)"   -> division (ignored)
    Customer band       "<PARTY>  SET-n - <CITY> (<code>)"      -> party_name + city
    item lines          "<ITEM (code)>  <Qty> <Free> <Value> <TQty> <TFree> <TVal>"
Per-customer subtotal rows (blank Item, repeated totals) and the printed
"Grand Total 2310 306 440114.22" are skipped.

Why positional (word x-coordinates), not flat text: this two-column PDF suffers
heavy character-bleed — the FIRST item line of every customer has the customer
heading re-printed *interleaved* into the item name at the glyph level
("KANLAIMOR STLAIA MLBIEOCD..." = "NIOSALIC 6 OINT (XA0169)" woven through
"AARTI MEDICAL STORE ..."). So we:
  * cluster words into baseline rows,
  * bucket the trailing numbers into their column by right-edge (x1) x-band,
  * read qty/free/amount from the always-clean "Total *" columns (the per-item
    Qty/Free/Value bleed into the name on first rows; the Total columns never do
    and, being a single-period report, equal the per-item values), and
  * recover the item name by removing the known customer-heading string (from the
    clean band line just above) as a character subsequence from the bled glyphs.

Reconciles: summed Total Qty / Free / Value == printed Grand Total
(2310 / 306 / 440114.22) on the reference file.
"""
import io
import re

_NUM = re.compile(r"^-?\d[\d,]*\.?\d*$")

# Numeric column right-edge (x1) bands. Numbers are right-aligned, so x1 is the
# stable anchor. Per-item Qty/Free/Value AND the Total Qty/Free/Value trio.
_BANDS = [
    ("qty", 200, 238),
    ("free", 250, 288),
    ("val", 298, 362),
    ("tqty", 383, 417),
    ("tfree", 423, 457),
    ("tval", 458, 532),
]

_NAME_MAX_X = 190  # left/name region ends before the first numeric column

H = ["Division", "Party Name", "Party Location", "Product Name", "Pack",
     "Qty", "Free Qty", "Amount"]

# division / manufacturer band. Two vendor spellings share the "KLM" stem:
#   VENUS  ->  "KLM LABORATORIES -COSMOCOR (XA0001)"
#   IMEX   ->  "KLM (COSMO DIV)-000845 (000845)"  /  "KLM (DERMA DIV) (MF0017)"
# Both are unambiguous manufacturer headers (no real customer is named "KLM ...").
# "LABOR" (not "LABORAT") also catches the last-page glyph-typo "KLM LABORETIRES".
_DIV_BAND = re.compile(r"^KLM\s+(?:LABOR|\(.*\bDIV\b)", re.I)
# trailing "(code)" on a band line
_CODE_TAIL = re.compile(r"\s*\(([0-9A-Za-z]{2,10})\)\s*$")
# repeating page furniture. NB "venus\s+pharma" (the vendor header), NOT a bare
# "venus" — a real customer is named "VENUS PHARMACY" and must not be swallowed as
# furniture (doing so desyncs the first-item pointer and garbles that item's name).
_FURNITURE = re.compile(
    r"^(venus\s+pharma\b|plot\s+no|sales\s+analysis|item\s+qty\s+free|manufacturer$|"
    r"customer$|total\s*-->|#value\b|page\b)",
    re.I,
)


def _to_f(t):
    try:
        return float(t.replace(",", ""))
    except ValueError:
        return 0.0


def _cluster(words, tol=3):
    """Group words into baseline rows (tops within `tol` px)."""
    ws = sorted(words, key=lambda w: (round(w["top"]), w["x0"]))
    lines, cur, top = [], [], None
    for w in ws:
        if top is None or abs(w["top"] - top) <= tol:
            cur.append(w)
            top = w["top"] if top is None else top
        else:
            lines.append(sorted(cur, key=lambda x: x["x0"]))
            cur, top = [w], w["top"]
    if cur:
        lines.append(sorted(cur, key=lambda x: x["x0"]))
    return lines


def _cluster_chars(chars, tol=3):
    cs = sorted(chars, key=lambda c: (round(c["top"]), c["x0"]))
    lines, cur, top = [], [], None
    for c in cs:
        if top is None or abs(c["top"] - top) <= tol:
            cur.append(c)
            top = c["top"] if top is None else top
        else:
            lines.append(sorted(cur, key=lambda x: x["x0"]))
            cur, top = [c], c["top"]
    if cur:
        lines.append(sorted(cur, key=lambda x: x["x0"]))
    return lines


def _band_values(line):
    """Right-edge-bucketed numeric tokens of a word-row -> {col: text}."""
    v = {}
    for w in line:
        if _NUM.match(w["text"]):
            x1 = w["x1"]
            for name, a, b in _BANDS:
                if a <= x1 <= b:
                    v[name] = w["text"]
                    break
    return v


def _split_party(band_text):
    """"<PARTY>  SET-n - <CITY> (code)"  ->  (party_name, city)."""
    text = _CODE_TAIL.sub("", band_text).strip()
    city = ""
    name = text
    if " - " in text:
        left, right = text.rsplit(" - ", 1)
        left = left.strip()
        right = right.strip(" -.,")
        if left:
            name = left
            city = right
    return name.strip(" -.,"), city


def _in_num_band(x1):
    return any(a <= x1 <= b for _, a, b in _BANDS)


# first "NAME (code)" segment used to locate the item name in a de-bled string
_ITEM_CODE = re.compile(r"\(([0-9A-Za-z][0-9A-Za-z\-\*/ ]{1,12})\)")


def _stream_lines(page, tol=3):
    """Baseline rows in NATIVE PDF stream order (chars NOT x-sorted).

    The two-column text layer overlaps the manufacturer + customer headings with
    the first item name at the same baseline, so x-sorting interleaves them into
    glyph soup. The raw emission order, however, is clean and sequential
    ("<MFR (code)><CUSTOMER (code)><ITEM (code)><numbers>"), so we cluster by top
    only, preserving each glyph's original stream position within the row.
    """
    out = {}
    cur, top = [], None
    for c in page.chars:  # already in stream order
        if top is None or abs(c["top"] - top) <= tol:
            cur.append(c)
            top = c["top"] if top is None else top
        else:
            if cur:
                out.setdefault(round(cur[0]["top"]), []).append(
                    "".join(x["text"] for x in cur)
                )
            cur, top = [c], c["top"]
    if cur:
        out.setdefault(round(cur[0]["top"]), []).append(
            "".join(x["text"] for x in cur)
        )
    # a single baseline may split into >1 stream chunk; join in order
    return {t: "".join(parts) for t, parts in out.items()}


def _strip_band_prefix(s, band):
    """Drop a leading band from `s`, tolerating whitespace differences.

    The band text comes from ``extract_words`` (spaces collapsed) while `s` is the
    raw stream (runs of spaces preserved), so we match char-by-char skipping any
    whitespace on either side. Returns the leftover, or the original `s` if `band`
    is not a prefix.
    """
    b = (band or "").strip()
    if not b:
        return s
    i = j = 0
    while j < len(b):
        if b[j].isspace():
            j += 1
            continue
        while i < len(s) and s[i].isspace():
            i += 1
        if i >= len(s) or s[i] != b[j]:
            return s  # not a real prefix — leave untouched
        i += 1
        j += 1
    return s[i:]


def _ws_find(haystack, needle):
    """Whitespace-tolerant substring search. Returns the index in `haystack` one
    past the end of the first `needle` occurrence (both compared with all whitespace
    ignored), or -1. Used to locate the customer band inside the raw stream even
    though the band text (from extract_words) has spaces collapsed and the stream
    does not, and the band may sit AFTER a (possibly corrupted) manufacturer band."""
    n = re.sub(r"\s+", "", needle or "")
    if not n:
        return -1
    # map each non-space haystack char to its original index
    comp = []
    pos = []
    for hi, ch in enumerate(haystack):
        if not ch.isspace():
            comp.append(ch)
            pos.append(hi)
    comp = "".join(comp)
    k = comp.find(n)
    if k < 0:
        return -1
    return pos[k + len(n) - 1] + 1


def _recover_item_name_stream(stream_text, div_raw, party_raw):
    """Recover the (bled) item name from a first-item row via PDF STREAM ORDER.

    The raw stream of a first-item baseline is emitted cleanly and sequentially as
    "<MANUFACTURER (code)><CUSTOMER (code)><ITEM (code)><numbers>". The CUSTOMER band
    is always printed intact, so we locate it inside the stream (whitespace-tolerant)
    and keep the text that follows, up to the item's own trailing "(code)". Anchoring
    on the customer band — rather than stripping a *known* manufacturer prefix — also
    survives a glyph-corrupted manufacturer header on the final page
    ("KLM LABORETIRES (COSMOQ)"). Returns "" when the anchor is not found so the
    caller can fall back to the legacy de-bleed.
    """
    s = (stream_text or "").strip()
    if not s:
        return ""
    end = _ws_find(s, party_raw)
    if end < 0:
        # party band not a clean prefix — try dropping a leading manufacturer band
        # first (covers rare ordering), then re-anchor on the party band anywhere.
        stripped = _strip_band_prefix(s, div_raw).strip()
        end = _ws_find(stripped, party_raw)
        s = stripped
    if end < 0:
        return ""
    tail = s[end:].strip()
    if not tail:
        return ""
    m = _ITEM_CODE.search(tail)
    if m:
        return tail[: m.end()].strip()
    m2 = re.search(r"\d", tail)
    if m2:
        return tail[: m2.start()].strip()
    return tail.strip()


def _recover_item_name(char_line, party_text):
    """Recover the (bled) item name from a first-item glyph row.

    The customer heading is re-printed interleaved into the item glyphs. We drop
    the actual value digits (numeric-band digit glyphs), then remove the known
    customer-heading characters as a left-to-right subsequence; the leftover
    glyphs, up to the item's own "(code)", are the item name.
    """
    keep = []
    for c in char_line:
        ch = c["text"]
        if _in_num_band(c["x1"]) and (ch.isdigit() or ch in ".,"):
            continue
        keep.append(ch)
    garb = re.sub(r"\s+", "", "".join(keep))
    tmpl = re.sub(r"\s+", "", party_text)
    used = [False] * len(garb)
    ti = 0
    for gi, ch in enumerate(garb):
        if ti < len(tmpl) and ch == tmpl[ti]:
            used[gi] = True
            ti += 1
    leftover = "".join(garb[i] for i in range(len(garb)) if not used[i])
    # keep up to and including the item's own (code)
    m = re.search(r"\([0-9A-Z][0-9A-Z\- ]{1,10}\)", leftover)
    if m:
        leftover = leftover[: m.end()]
    return leftover.strip()


def _spaceify(compact):
    """Insert spaces into a de-bled compact item name so it reads naturally
    (before letter->digit / digit->letter transitions and before "(")."""
    if not compact:
        return compact
    out = [compact[0]]
    for prev, ch in zip(compact, compact[1:]):
        if ch == "(":
            out.append(" ")
        elif prev.isalpha() and ch.isdigit():
            out.append(" ")
        elif prev.isdigit() and ch.isalpha():
            out.append(" ")
        out.append(ch)
    return re.sub(r"\s+", " ", "".join(out)).strip()


def parse_marg_sales_analysis_pdf(text, file_bytes=None):
    if not file_bytes:
        return H, []

    import pdfplumber

    rows = []
    party_name = party_city = division = ""
    party_raw = div_raw = ""  # full band text as printed (SET-n + code intact)
    first_item_pending = False  # first item after a customer band is glyph-bled
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            char_lines = {}
            for cl in _cluster_chars(list(page.chars)):
                char_lines[round(cl[0]["top"])] = cl
            stream_lines = _stream_lines(page)
            for wl in _cluster(page.extract_words(x_tolerance=1.5)):
                joined = " ".join(w["text"] for w in wl).strip()
                if not joined or _FURNITURE.match(joined):
                    continue
                low = joined.lower()
                if low.startswith("grand total") or "total -->" in low:
                    continue

                vals = _band_values(wl)
                name_toks = [w["text"] for w in wl if w["x0"] < _NAME_MAX_X]
                left_text = " ".join(name_toks).strip()
                has_total = "tval" in vals

                # ---- band line: no Total-Value column, ends with "(code)" -----
                # A manufacturer/customer band never carries the Total-Value trio
                # (x1>=458). We key off the ABSENCE of "tval" rather than of ALL
                # numbers, because a party name can legitimately end in a digit that
                # lands in the qty x-band (e.g. "SHREE JAY AMBE MEDICAL STORE 12"),
                # which must NOT demote the band into an item and desync the
                # first-item pointer.
                if "tval" not in vals and left_text and _CODE_TAIL.search(joined):
                    if _DIV_BAND.match(joined):
                        division = _CODE_TAIL.sub("", joined).strip()
                        div_raw = joined
                    else:
                        party_name, party_city = _split_party(joined)
                        party_raw = joined
                        first_item_pending = True
                    continue

                # ---- subtotal row: numbers but NO name text ------------------
                if not left_text:
                    continue

                # ---- item line: has the Total-Value column + a name ----------
                if not has_total or not party_name:
                    continue

                qty = _to_f(vals.get("tqty", "0"))
                free = _to_f(vals.get("tfree", "0"))
                amount = _to_f(vals.get("tval", "0"))
                if qty == 0 and free == 0 and amount == 0:
                    continue

                # item name — clean when 2nd+ item of a party; bled on the FIRST
                # item of a party (customer heading re-printed into the glyphs),
                # so reconstruct from glyphs against the customer heading.
                bled = first_item_pending
                first_item_pending = False
                top = round(wl[0]["top"])
                cl = char_lines.get(top) or char_lines.get(top + 1) or char_lines.get(top - 1)
                heading = (party_name + " " + party_city).strip()
                if bled:
                    # PRIMARY: clean recovery from native stream order (mfr + party
                    # bands were emitted before the item, so stripping those literal
                    # prefixes yields the item name intact — no glyph soup).
                    stream = (stream_lines.get(top) or stream_lines.get(top + 1)
                              or stream_lines.get(top - 1) or "")
                    product = _recover_item_name_stream(stream, div_raw, party_raw)
                    # FALLBACK: legacy x-sorted subsequence de-bleed if stream recovery
                    # produced nothing usable (empty, or still carried a heading tail).
                    if (not product) and cl is not None:
                        product = _spaceify(_recover_item_name(cl, heading))
                else:
                    # trim any trailing numeric columns that slipped into `joined`
                    product = re.split(r"\s+\d[\d,]*\.?\d*(?:\s|$)", joined)[0].strip()
                if not product:
                    product = left_text

                rows.append([division, party_name, party_city, product, "",
                             qty, free, amount])
    return H, rows
