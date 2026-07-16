import io
import re

# ---------------------------------------------------------------------------
# NILKANTH PHARMA (KLM distributor, AMRELI) — "Product Summary" party sales.
# Source file: NILKANTH PHARMA/Party report/klm party.pdf
#
# Furniture (repeated every page):
#   "NILKANTH PHARMA"                              (vendor banner)
#   "NR.HOTEL AVADH,..." / "AMRELI-365601" / "Phone No. :..."   (address)
#   "Product Summary"
#   "From: DD-MM-YYYY To: DD-MM-YYYY"
#   column header (GATE token, spaces stripped/lowercased):
#       "Product Pack Qty Free Rate Amount"  ->  "productpackqtyfreerateamount"
#   "Page N of M"
#
# Body (three levels):
#   * COMPANY band  — "KLM LABORATORIES PVT. LTD. KLM (COSMO)" : a manufacturer
#     line ending in a "KLM (...)" division tag. Carried down as division. It
#     carries NO commas outside the paren and NO numeric tail.
#   * PARTY band    — "KRISHNA MEDICAL STORES, DHARI, DHARI" : a comma-delimited
#     "<NAME>, <TOWN>, <TOWN>" line with NO numeric tail. party_name = the text
#     before the first comma; party_location = the middle comma segment (town).
#   * PRODUCT row   — "EKRAN AQUA GEL 50GM. 10*50 GM. 5 2 257.63 1288.15" :
#     Product | Pack | Qty | Free | Rate | Amount.
#   * "Party Total -> ..." / "Grand Total -> ..." roll-ups (skipped).
#
# COLUMN SPLIT is POSITIONAL by word x-coordinate — the six columns are cleanly
# aligned in the source (header x0: Product 58, Pack 208, Qty 301, Free 362,
# Rate 423, Amount 469). A purely text-based split is unsafe here because product
# names themselves end in pack-like fragments ("EKRAN AQUA GEL 50GM.",
# "KLM KLIN FACE WASH 100ML B", "TECUM 0.03% OIT.") that a right-to-left pack
# peel would wrongly swallow. Using x-coordinates the Product column (x0 < 205)
# and the Pack column (205 <= x0 < 300) never overlap.
#
# Numeric columns are mapped by their fixed x-band, NEVER derived:
#   Qty (int, 300 <= x0 < 362), Free (int or "-", 362 <= x0 < 410),
#   Rate (decimal, 410 <= x0 < 462), Amount (decimal, x0 >= 462).
# Free "-" -> "0". Reconcile (source's own arithmetic): Qty * Rate == Amount and
# per-party Qty/Free/Amount sums equal the printed "Party Total ->" line; the
# Qty=114, Free=26, Amount=17417.93 grand total matches the summed rows.
# ---------------------------------------------------------------------------

H = [
    "Party Name",
    "Party Location",
    "Division",
    "Product Name",
    "Pack",
    "Qty",
    "Free Qty",
    "Rate",
    "Amount",
]

# Column x0 boundaries (left edge of each column), with generous tolerance.
_PACK_X0 = 205.0    # product < this <= pack
_QTY_X0 = 300.0     # pack   < this <= qty
_FREE_X0 = 362.0
_RATE_X0 = 410.0
_AMOUNT_X0 = 462.0

_MONEY = re.compile(r"^-?[\d,]+\.\d{1,2}$")
_INT = re.compile(r"^-?\d+$")

# A company band ends in a "KLM (...)" division tag.
_COMPANY = re.compile(r"\bKLM\s*\([^)]*\)?\s*$", re.I)


def _fnum(tok):
    try:
        return float(str(tok).replace(",", ""))
    except (ValueError, AttributeError):
        return 0.0


def _fmt(x):
    return "%.2f" % x


def _is_chrome(su):
    return (
        not su
        or su.startswith("NILKANTH PHARMA")
        or su.startswith("PRODUCT SUMMARY")
        or su.startswith("PRODUCT PACK")
        or su.startswith("FROM:")
        or su.startswith("FROM :")
        or su.startswith("PAGE ")
        or su.startswith("PHONE NO")
        or su.startswith("NR.")
        or su.startswith("AMRELI-")
        or su.startswith("PARTY TOTAL")
        or su.startswith("GRAND TOTAL")
    )


def _row_words(page):
    """Group a page's words into visual text rows.

    Words on one printed line share a 'top' to sub-pixel jitter; a hard modulo
    bucket (round(top/2)) can straddle a boundary and split a row's numeric tail
    onto its own bucket. Cluster instead: sort by top and open a new row only
    when the gap to the current row's anchor exceeds a small tolerance."""
    words = sorted(page.extract_words(), key=lambda w: (w["top"], w["x0"]))
    out = []
    anchor = None
    cur = []
    for w in words:
        if anchor is None or abs(w["top"] - anchor) <= 3.0:
            if anchor is None:
                anchor = w["top"]
            cur.append(w)
        else:
            out.append(sorted(cur, key=lambda x: x["x0"]))
            cur = [w]
            anchor = w["top"]
    if cur:
        out.append(sorted(cur, key=lambda x: x["x0"]))
    return out


def _column_split(ws):
    """Bucket a product row's words by x0 into the 6 columns. Returns
    (product, pack, qty, free, rate, amount) as strings, or None if the row has
    no numeric tail (i.e. it is a band / header, not a product line)."""
    prod, pack, qty, free, rate, amount = [], [], [], [], [], []
    for w in ws:
        x0 = w["x0"]
        t = w["text"]
        if x0 < _PACK_X0:
            prod.append(t)
        elif x0 < _QTY_X0:
            pack.append(t)
        elif x0 < _FREE_X0:
            qty.append(t)
        elif x0 < _RATE_X0:
            free.append(t)
        elif x0 < _AMOUNT_X0:
            rate.append(t)
        else:
            amount.append(t)
    qty_s = " ".join(qty).strip()
    rate_s = " ".join(rate).strip()
    amount_s = " ".join(amount).strip()
    # A real product row has an integer Qty, a decimal Rate and a decimal Amount.
    if not (_INT.match(qty_s) and _MONEY.match(rate_s) and _MONEY.match(amount_s)):
        return None
    free_s = " ".join(free).strip()
    if free_s in ("-", ""):
        free_s = "0"
    return (
        " ".join(prod).strip(),
        " ".join(pack).strip(),
        qty_s,
        free_s,
        rate_s,
        amount_s,
    )


def _split_party(line):
    """"NAME, TOWN, TOWN" -> (name, town)."""
    parts = [p.strip() for p in line.split(",")]
    name = parts[0]
    town = parts[1] if len(parts) >= 2 else ""
    return name, town


def parse_r15_nilkanth_product_summary_pack(text, file_bytes=None):
    if not file_bytes:
        return H, []
    import pdfplumber

    rows = []
    division = ""
    party_name = ""
    party_town = ""

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            for ws in _row_words(page):
                line = " ".join(w["text"] for w in ws).strip()
                su = line.upper()
                if _is_chrome(su):
                    continue

                cols = _column_split(ws)
                if cols is not None:
                    prod, pack, qty, free, rate, amount = cols
                    if not prod:
                        continue
                    rows.append([
                        party_name,
                        party_town,
                        division,
                        prod,
                        pack,
                        qty,
                        free,
                        rate,
                        amount,
                    ])
                    continue

                # Not a product row -> a band. Company band ends in "KLM (...)".
                if _COMPANY.search(line):
                    division = line
                    continue
                # Otherwise a party band ("NAME, TOWN, TOWN").
                if "," in line and re.search(r"[A-Za-z]", line):
                    party_name, party_town = _split_party(line)

    return H, rows
