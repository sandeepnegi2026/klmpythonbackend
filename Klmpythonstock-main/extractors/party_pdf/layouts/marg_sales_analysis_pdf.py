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

# division / manufacturer band ("KLM LABORATORIES ...")
_DIV_BAND = re.compile(r"^KLM\s+LABORAT", re.I)
# trailing "(code)" on a band line
_CODE_TAIL = re.compile(r"\s*\(([0-9A-Za-z]{2,10})\)\s*$")
# repeating page furniture
_FURNITURE = re.compile(
    r"^(venus\b|plot\s+no|sales\s+analysis|item\s+qty\s+free|manufacturer$|"
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
    first_item_pending = False  # first item after a customer band is glyph-bled
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            char_lines = {}
            for cl in _cluster_chars(list(page.chars)):
                char_lines[round(cl[0]["top"])] = cl
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

                # ---- band line: no numeric columns, ends with "(code)" --------
                if not vals and left_text and _CODE_TAIL.search(joined):
                    if _DIV_BAND.match(joined):
                        division = _CODE_TAIL.sub("", joined).strip()
                    else:
                        party_name, party_city = _split_party(joined)
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
                if bled and cl is not None:
                    product = _spaceify(_recover_item_name(cl, heading))
                else:
                    # trim any trailing numeric columns that slipped into `joined`
                    product = re.split(r"\s+\d[\d,]*\.?\d*(?:\s|$)", joined)[0].strip()
                if not product:
                    product = left_text

                rows.append([division, party_name, party_city, product, "",
                             qty, free, amount])
    return H, rows
