import io
import re

# Column x-boundaries observed in the SwilERP "Product-Customer Wise Sales"
# fixed-column layout (CAPITAL PHARMA AGENCIES):
#   Customer  x0  7..~200      Station  x0 ~343..    Qty  right ~668    Value right ~792
# The name<->station split is genuinely ambiguous in the flat text
# (e.g. "SEN BROTHERS P.S.-HARE STREE", "LIFE LINE JADAVPUR MEHTA BUILDING"),
# so this parser reads word x-coordinates to slice the columns positionally.
#
# These constants are only the FALLBACK: SwilERP prints the same report at
# different widths (SRI RAM MEDISALES uses Station~233 / Qty right~459 /
# Value right~551, far left of these defaults), so the boundaries are derived
# per page from the "Customer  Station  Qty.  Sales Value" header row whenever
# that header is found (see _header_bounds).
_STATION_X = 330   # station column starts ~343
_QTY_X = 600       # qty column ~654-668
_VAL_X = 720       # value column ~751-792

_VAL_RE = re.compile(r"^-?\d[\d,]*\.\d{1,2}$")
_QTY_RE = re.compile(r"^-?\d[\d,]*(?:\.\d+)?$")
# a product-code leading token: letters immediately followed by a dot or digit
# (KLM2.11, KLM119, KLM.11, KLM9004) — distinguishes a PRODUCT band from a
# DIVISION band (bare "KLM PEDIA", "KLM COSMOCOR").
_CODE_RE = re.compile(r"^[A-Za-z]{1,6}[.\d][\w.\-/]*$")
# SRI RAM MEDISALES variant: all-digit / digit-leading product codes
# ("02033", "5469", "027", "36549+").
_NUMCODE_RE = re.compile(r"^\d[\w.\-/+]*$")
# SRI RAM MEDISALES variant: bare-letter product codes ("EXG", "MED", "SBMO").
# Only treated as a code when the line also carries a pack token (a word with a
# digit) at/right of the station column — a DIVISION band like "KLM LABS 2"
# keeps its digit inside the customer column, so it stays a division.
_ALPHACODE_RE = re.compile(r"^[A-Za-z]{2,6}$")
_PACKISH = re.compile(r"\d")


def _is_furniture(joined):
    low = joined.lower()
    if not joined:
        return True
    if low.startswith("page no") or "continued" in low or "powered by" in low:
        return True
    if low.startswith("customer station") or low.startswith("customer  station"):
        return True
    if "capital pharma" in low or "b.r.b.basu" in low or "product-customer wise" in low:
        return True
    if joined.startswith("TOTAL") or joined.startswith("GRAND TOTAL"):
        return True
    # separators / band terminators made only of dashes / asterisks
    if re.fullmatch(r"[-*\s]+", joined):
        return True
    return False


def _num(t):
    return t.replace(",", "")


def _header_bounds(linemap):
    """Derive the column x-boundaries from this page's own
    "Customer  Station  Qty.  Sales Value" header row.

    SwilERP prints this report at different column widths per stockist
    (CAPITAL: Station@343/Qty@643/Sales@731 — SRI RAM: Station@233/Qty@438/
    Sales@493), so the hardcoded module constants only fit the wide variant.
    Returns (station_x, qty_x, val_x) or None when no header row is on the page
    (caller then keeps the previous page's bounds / module defaults).
    The offsets are chosen so the WIDE variant derives (338, 603, 726) —
    classification-identical to the original constants (330, 600, 720).
    """
    for top in sorted(linemap):
        ws = sorted(linemap[top], key=lambda w: w["x0"])
        if len(ws) >= 4 and ws[0]["text"] == "Customer":
            names = {w["text"].rstrip("."): w for w in ws}
            if "Station" in names and "Qty" in names and "Sales" in names:
                return (
                    names["Station"]["x0"] - 5,   # station data left-aligns at header x0
                    names["Qty"]["x0"] - 40,      # qty right-aligned under header; pad left
                    names["Sales"]["x0"] - 5,     # value right-aligned right of "Sales"
                )
    return None


def parse_product_customer_wise_sales(text, file_bytes=None):
    """SwilERP 'Product-Customer Wise Sales' (CAPITAL PHARMA AGENCIES).

    Nesting:  DIVISION band ("KLM PEDIA")  ->  PRODUCT band ("KLM2.11 KLM D3
    NANO DROP 15ML")  ->  customer rows ("TAPAN MEDICO  KOLKATA  6  535.74")
    ->  "TOTAL <qty> <amount>" subtotal.  Each customer row becomes one output
    record (party=customer, area=station, product=current band product).

    Positional: word x0 slices Customer | Station | Qty | Value cleanly, which
    the flat text cannot (customer name and station both run together).
    """
    headers = ["Division", "Party Name", "Area", "Product Name", "Qty", "Amount"]
    if not file_bytes:
        return headers, []

    import pdfplumber

    rows = []
    division = ""
    product = ""
    station_x, qty_x, val_x = _STATION_X, _QTY_X, _VAL_X
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            linemap = {}
            for w in page.extract_words():
                linemap.setdefault(round(w["top"]), []).append(w)
            hb = _header_bounds(linemap)
            if hb:
                station_x, qty_x, val_x = hb
            for top in sorted(linemap):
                ws = sorted(linemap[top], key=lambda w: w["x0"])
                joined = " ".join(w["text"] for w in ws)
                if _is_furniture(joined):
                    continue

                # --- customer data row: numeric value in the value column + a qty ---
                val_words = [w for w in ws if w["x0"] >= val_x and _VAL_RE.match(w["text"])]
                qty_words = [w for w in ws if qty_x <= w["x0"] < val_x and _QTY_RE.match(w["text"])]
                if val_words and qty_words:
                    name = " ".join(w["text"] for w in ws if w["x0"] < station_x).strip()
                    station = " ".join(
                        w["text"] for w in ws if station_x <= w["x0"] < qty_x
                    ).strip()
                    if not name:
                        continue
                    qty = _num(qty_words[-1]["text"])
                    amt = _num(val_words[-1]["text"])
                    rows.append([division, name, station, product, qty, amt])
                    continue

                # --- band line (no value column) ---
                tok0 = ws[0]["text"]
                is_code = bool(_CODE_RE.match(tok0)) or (
                    len(tok0) >= 2 and bool(_NUMCODE_RE.match(tok0))
                )
                if not is_code and _ALPHACODE_RE.match(tok0) and ws[0]["x0"] < 100 and len(ws) >= 3:
                    # bare-letter product code: require a pack token (digit) at/right
                    # of the station column so "KLM LABS 2" stays a division band
                    if any(_PACKISH.search(w["text"]) and w["x0"] >= station_x for w in ws[1:]):
                        is_code = True
                if is_code and len(ws) > 1:
                    # product band: name = everything after the code token
                    parts = [w["text"] for w in ws[1:]]
                    # collapse a trailing duplicated pack token ("... 15ML 15ML")
                    if len(parts) >= 2 and parts[-1] == parts[-2] and _PACKISH.search(parts[-1]):
                        parts = parts[:-1]
                    product = " ".join(parts).strip()
                elif re.search(r"[A-Za-z]", joined):
                    # centered letterhead (vendor name / address, x0 well right of
                    # the customer column) is page furniture, not a division band
                    if ws[0]["x0"] > 150:
                        continue
                    # division / company band
                    division = joined.strip()
    return headers, rows
