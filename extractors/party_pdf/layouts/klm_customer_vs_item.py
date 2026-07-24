import io
import re
from collections import defaultdict

import pdfplumber

# ---------------------------------------------------------------------------
# KLM "Customer VS Item Details" party layout (BASHA MEDICAL AND FANCY, ONGOLE).
#
# Title band:  "Customer VS Item Details 01/May/2026 To 31/May/2026"
# Column header (split across two physical lines):
#   Item name | Item Pack | Town | Bill Date | Bill No. | Batch No | MRP | Qty |
#   Free | Replace | Rate | Gross Value | Gross-Discount | Tax% | Tax Value |
#   Net Value
#
# Each customer is a BAND row of the form "NAME,TOWN" (mixed/upper case, no
# trailing number run) e.g. "DEEPTHI MEDICALS,ONGOLE", "SUDHA PHARAMCY,ONGOLE".
# Product line items follow. A data row is:
#   <ItemName> <Town> dd/mm/yyyy <BillNo e.g. "WS 89"> <Batch> <MRP> <Qty>
#   [Free] [Replace] <Rate> <Gross> <GrossDisc> <Tax%> <TaxValue> <NetValue>
# with the product NAME wrapping onto 1-2 continuation lines BELOW the row
# (e.g. "NIOSOL-F 20GM ... 4,125.03" then "CREAM").
#
# CRITICAL: Free and Replace are usually BLANK in the interior of a row, so a
# flat-text split mis-assigns the trailing numbers. We therefore parse by word
# x-position (pdfplumber extract_words) and bucket each numeric token into the
# column whose x-range it falls in. Qty and NetValue are the reconciliation
# targets (per-band "Totals" and a final "Grand Total").
# ---------------------------------------------------------------------------

H = [
    "Party Name",
    "Product Name",
    "Pack",
    "Town",
    "Date",
    "Bill No",
    "Batch",
    "MRP",
    "Qty",
    "Free",
    "Rate",
    "Amount",
]

NUM = re.compile(r"^-?[\d,]+\.\d{1,2}$")
DATE = re.compile(r"\b\d{2}/\d{2}/\d{4}\b")

# Column right-aligned anchors (x-centre) observed in the export; bucket each
# numeric token by nearest boundary. Boundaries are the midpoints between
# adjacent column centres. Replace/Tax% are dropped from the emitted row.
_COL_CENTERS = [
    ("mrp", 412.0),
    ("qty", 455.0),
    ("free", 487.0),
    ("replace", 527.0),
    ("rate", 572.0),
    ("gross", 619.0),
    ("grossdisc", 669.0),
    ("taxpct", 712.0),
    ("taxval", 767.0),
    ("net", 819.0),
]


def _colof(cx):
    best = None
    bd = 1e9
    for name, c in _COL_CENTERS:
        d = abs(cx - c)
        if d < bd:
            bd = d
            best = name
    return best


def _cluster(words, tol=4.0):
    """Group extract_words into visual lines by 'top' (numbers on a data row sit
    ~1px off the item-name baseline, so a tolerance merges them)."""
    ws = sorted(words, key=lambda w: (w["top"], w["x0"]))
    lines = []
    cur = []
    ct = None
    for w in ws:
        if ct is None or abs(w["top"] - ct) <= tol:
            cur.append(w)
            if ct is None:
                ct = w["top"]
        else:
            lines.append(cur)
            cur = [w]
            ct = w["top"]
    if cur:
        lines.append(cur)
    return lines


def _fnum(tok):
    try:
        return float(tok.replace(",", ""))
    except (ValueError, AttributeError):
        return 0.0


def _is_band(text):
    """A customer band: contains a comma, has letters, and no dd/mm/yyyy date
    and no rupee-decimal numeric run. Rejects headers/totals/noise."""
    s = text.strip()
    if not s or "," not in s:
        return False
    if DATE.search(s):
        return False
    up = s.upper()
    if up.startswith(("TOTALS", "GRAND TOTAL", "PAGE ", "ITEM NAME", "CUSTOMER VS")):
        return False
    if up.startswith(("BASHA", "D.NO", "PACK ", "PACK\t")):
        return False
    # must start with a letter (party name)
    if not re.match(r"[A-Za-z]", s):
        return False
    # no decimal-money tokens (a data line has them, a band does not)
    if any(NUM.match(t) for t in s.split()):
        return False
    return True


# Business-type suffix words that must never be promoted to a town (guards the
# trailing-comma fallback below).
_BIZ_SUFFIX = {
    "MEDICALS", "MEDICAL", "MEDICOSE", "MEDICOS", "MEDICO", "PHARMACY",
    "PHARMA", "PHARAMCY", "STORES", "STORE", "AGENCIES", "AGENCY",
    "DISTRIBUTORS", "DISTRIBUTOR", "CHEMIST", "CHEMISTS", "DRUG", "DRUGS",
    "ENTERPRISES", "TRADERS", "FANCY", "GENERAL", "SURGICALS", "AND", "GEN",
    "CO", "HOSPITAL", "CLINIC", "CARE",
}


def _split_party_area(raw):
    raw = re.sub(r"\s*\(Contd\.,?\)\s*$", "", raw, flags=re.IGNORECASE).strip()
    trailing_comma = raw.endswith(",")
    raw = raw.rstrip(", ").strip()
    if "," in raw:
        head, _, tail = raw.rpartition(",")
        name = head.strip()
        area = tail.strip()
        if not name:  # e.g. ",ONGOLE" -> fall back
            name, area = area, ""
        return name, area
    # Trailing-comma band with an EMPTY town slot (e.g. "PAVAN MEDICALS NELLURE,")
    # means the town was folded into the name field. Promote the last word as the
    # town when the name still has >=2 other words and that word is not a
    # business-type suffix. Name is left intact (party identity), area is filled.
    if trailing_comma:
        words = raw.split()
        if len(words) >= 3 and words[-1].upper().strip(".") not in _BIZ_SUFFIX:
            return raw, words[-1]
    return raw, ""


def _is_noise(up):
    return (
        not up
        or up.startswith("BASHA MEDICAL")
        or up.startswith("D.NO")
        or up.startswith("CUSTOMER VS ITEM")
        or up.startswith("ITEM NAME")
        or up.startswith("PACK ")
        or up == "PACK"
        or up.startswith("PAGE ")
        or up.startswith("TOTALS")
        or up.startswith("GRAND TOTAL")
        or up.startswith("E VALUE")          # header wrap "Replace Value"
        or up.startswith("SCOUNT")           # header wrap "Gross-Discount"
    )


def parse_klm_customer_vs_item(text, file_bytes=None):
    rows = []
    if not file_bytes:
        return H, rows

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            if not words:
                continue
            lines = _cluster(words)

            party_name = ""
            party_area = ""
            pending = None  # the row currently accreting continuation-name lines

            def flush():
                nonlocal pending
                if pending is not None:
                    rows.append(pending)
                    pending = None

            for ln in lines:
                ln = sorted(ln, key=lambda w: w["x0"])
                txt = " ".join(w["text"] for w in ln).strip()
                up = txt.upper()

                nums = [w for w in ln if NUM.match(w["text"])]
                has_date = bool(DATE.search(txt))

                # ---- customer band ----------------------------------------
                if _is_band(txt):
                    flush()
                    party_name, party_area = _split_party_area(txt)
                    continue

                # ---- noise / totals / header ------------------------------
                if _is_noise(up):
                    flush()
                    continue

                # ---- product data row (date + numeric tail) ---------------
                if has_date and len(nums) >= 5:
                    flush()
                    # bucket numeric tokens by x-column
                    buckets = {}
                    for w in nums:
                        cx = (w["x0"] + w["x1"]) / 2.0
                        col = _colof(cx)
                        # keep the last (right-most) token per column
                        buckets[col] = w["text"]

                    qty = _fnum(buckets.get("qty", "0"))
                    free = _fnum(buckets.get("free", "0"))
                    rate = _fnum(buckets.get("rate", "0"))
                    mrp = _fnum(buckets.get("mrp", "0"))
                    net = _fnum(buckets.get("net", "0"))
                    gross = _fnum(buckets.get("gross", "0"))
                    amount = net if net else gross

                    # split the descriptive prefix (everything left of Town/date)
                    mdate = DATE.search(txt)
                    prefix = txt[: mdate.start()].strip()
                    # Town sits between item name and date; item words start col 0.
                    # Drop the trailing Town token (single word before the date)
                    # and pull Bill No / Batch which are also before the date's
                    # right side. We only need product name -> take words left of
                    # Town. Town is the last alpha word-group before the date whose
                    # x0 is in the Town column band (~140-200).
                    town = ""
                    name_words = []
                    pack_words = []
                    for w in ln:
                        if NUM.match(w["text"]):
                            continue
                        cx = (w["x0"] + w["x1"]) / 2.0
                        if DATE.match(w["text"]):
                            break
                        if 140.0 <= cx <= 200.0:  # Town column band
                            town = w["text"]
                            continue
                        # Pack is its own header column (x-centre ~118, between the
                        # Item-name column <100 and the Town band >=140). Keep it
                        # separate so the Pack size ("75GM") isn't fused into the
                        # product name and mis-guessed downstream (e.g. pack="SOAP").
                        if 100.0 <= cx < 140.0:
                            pack_words.append(w["text"])
                            continue
                        if cx < 100.0:
                            name_words.append(w["text"])
                    prod = " ".join(name_words).strip()
                    pack = " ".join(pack_words).strip()

                    # bill no (e.g. "WS 89") and batch land between date and MRP;
                    # capture bill no tokens with x in ~255-320, batch ~320-390
                    bill_toks = []
                    batch = ""
                    seen_date = False
                    for w in ln:
                        cx = (w["x0"] + w["x1"]) / 2.0
                        if DATE.match(w["text"]):
                            seen_date = True
                            continue
                        if not seen_date:
                            continue
                        if NUM.match(w["text"]):
                            continue
                        if 250.0 <= cx <= 320.0:
                            bill_toks.append(w["text"])
                        elif 320.0 <= cx <= 395.0:
                            batch = w["text"]
                    mdt = mdate.group(0) if mdate else ""
                    bill = " ".join(bill_toks).strip()

                    pending = [
                        party_name,
                        prod,
                        pack,
                        town or party_area,
                        mdt,
                        bill,
                        batch,
                        "%.2f" % mrp,
                        "%.2f" % qty,
                        "%.2f" % free,
                        "%.2f" % rate,
                        "%.2f" % amount,
                    ]
                    continue

                # ---- product-name continuation line -----------------------
                # letters, no date, no money tokens, not a band/noise -> append
                # onto the pending row's product name.
                if pending is not None and re.search(r"[A-Za-z]", txt) and not nums:
                    pending[1] = (pending[1] + " " + txt).strip()
                    continue

            flush()

    return H, rows
