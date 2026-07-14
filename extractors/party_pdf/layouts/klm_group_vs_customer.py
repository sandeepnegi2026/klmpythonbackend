import re

# ---------------------------------------------------------------------------
# KLM "Group Vs Customer Details" party layout
# (SRI SHIRIDI SAI MEDICAL DISTRIBUTORS, AMALAPURAM).
#
# Title band:  "Group Vs Customer Details From 01/Jun/26 To 30/Jun/26"
# Column header (one physical line, wraps "Name" onto the next):
#   Item Name / Customer Name | Town | Date | Number | Batch | MRP | Qty |
#   Free | Replace | Rate | Gross Value | Net Value
#
# Each customer is a BAND row "NAME (CODE)" whose code is a paren token
# e.g. "MOHAN MEDICAL&GEN STORES (AA56)".  In the flat text layer the band is
# followed by a TRUNCATED echo of the same name (e.g. "MOHAN MEDICAL&GEN ST"
# or "S K K MEDICAL STORES (T") which must be skipped.  In one dialect (klmp)
# the band's code itself is truncated to a bare "(" and there is no echo.
#
# Data rows are date-anchored (dd/Mon/yy).  TWO numeric-tail dialects occur:
#   * 5-num dialect (klmc, klmd): blank Free/Replace are DROPPED in flat text,
#       tail = MRP Qty Rate Gross Net
#       e.g. "KOJITIN EMULGEL AMALAP 11/Jun/26 GST 4385 BR3601 345 1 233.90 233.90 262.00"
#   * 7-num dialect (klmp): Free/Replace printed as 0.00,
#       tail = MRP Qty Free Replace Rate Gross Net
#       e.g. "MELAPIK HQ CREAM AMALAPURAM 18/Jun/26 GST 4820 BF502 145.00 2.00 0.00 0.00 103.57 207.14 218.00"
#
# Row shape (left of the numeric tail):
#   <item words...> <TOWN> <date> GST <billno> <batch> <tail>
#
# Column map:  Customer -> party_name, Town -> party_location,
#   Item Name -> product_name, GST <billno> -> invoice_number, date -> invoice_date,
#   Batch -> batch_no, MRP -> mrp, Qty -> qty, Free -> free_qty, Rate -> rate,
#   Gross Value -> amount, Net Value -> net_amount.
#
# Reconcile:  sum(qty) and sum(gross) equal the printed "Grand Total".
#   (Net value totals separately; the source Net line reconciles too.)
#
# Skipped: number-only per-customer subtotal lines and the "Grand Total" line.
# ---------------------------------------------------------------------------

H = [
    "Party Name",
    "Party Location",
    "Product Name",
    "Date",
    "Invoice Number",
    "Batch",
    "MRP",
    "Qty",
    "Free",
    "Rate",
    "Amount",
    "Net Amount",
]

# Money token (has a decimal point) or a bare integer.
_MONEY = re.compile(r"^-?[\d,]+\.\d{1,2}$")
_INT = re.compile(r"^-?\d+$")
_DATE = re.compile(r"\b\d{1,2}/[A-Za-z]{3}/\d{2,4}\b")
# Band ends with a paren customer-code: "(AA56)", "(T046", or a bare "(".
_BAND_TAIL = re.compile(r"\([A-Z]{0,3}\d*\)?\s*$")


def _fnum(tok):
    try:
        return float(str(tok).replace(",", ""))
    except (ValueError, AttributeError):
        return 0.0


def _fmt(x):
    return "%.2f" % x


def _is_band(line):
    s = line.strip()
    if not s or _DATE.search(s):
        return False
    up = s.upper()
    if up.startswith(("GROUP VS", "ITEM NAME", "ITEMNAME", "GRAND TOTAL", "PAGE ")):
        return False
    if not re.search(r"[A-Za-z]", s):
        return False
    # must end with a paren customer-code (complete or truncated)
    if not _BAND_TAIL.search(s):
        return False
    # a band carries no money tokens
    if any(_MONEY.match(t) for t in s.split()):
        return False
    return True


def _band_name(line):
    """Strip the trailing "(CODE)"/"(" from a band line -> customer name."""
    s = line.strip()
    s = re.sub(r"\s*\([A-Z0-9]*\)?\s*$", "", s).strip()
    return s


def _is_noise(line):
    up = line.strip().upper()
    return (
        not up
        or up.startswith("SRI SHIRIDI SAI")
        or up.startswith("#")
        or up.startswith("GROUP VS")
        or up.startswith("ITEM NAME")
        or up.startswith("ITEMNAME")
        or up == "NAME"
        or up.startswith("PAGE ")
        or up.startswith("GRAND TOTAL")
    )


def _parse_data_line(line):
    """Return (item, town, date, bill, batch, mrp, qty, free, rate, gross, net)
    or None if the line is not a product data row."""
    m = _DATE.search(line)
    if not m:
        return None
    date = m.group(0)
    left = line[: m.start()].strip()
    right = line[m.end():].strip()

    # LEFT part = "<item words> <TOWN>" ; TOWN is the last token.
    lw = left.split()
    if len(lw) < 2:
        return None
    town = lw[-1]
    item = " ".join(lw[:-1]).strip()

    # RIGHT part = "GST <billno> <batch> <numeric tail>"
    rw = right.split()
    # collect trailing numeric tokens
    tail = []
    i = len(rw) - 1
    while i >= 0 and (_MONEY.match(rw[i]) or _INT.match(rw[i])):
        tail.insert(0, rw[i])
        i -= 1
    head = rw[: i + 1]  # "GST <billno> <batch>"

    bill = ""
    batch = ""
    if head and head[0].upper() == "GST":
        bill = "GST " + (head[1] if len(head) > 1 else "")
        if len(head) > 2:
            batch = head[2]
    elif head:
        # no explicit GST token: first is bill, last is batch
        bill = head[0]
        if len(head) > 1:
            batch = head[-1]

    if len(tail) < 5:
        return None

    # Two dialects by tail length.
    if len(tail) >= 7:
        # MRP Qty Free Replace Rate Gross Net  (take last 7)
        t = tail[-7:]
        mrp, qty, free, _repl, rate, gross, net = t
    else:
        # 5-num: MRP Qty Rate Gross Net
        t = tail[-5:]
        mrp, qty, rate, gross, net = t
        free = "0"

    return (
        item,
        town,
        date,
        bill.strip(),
        batch,
        _fnum(mrp),
        _fnum(qty),
        _fnum(free),
        _fnum(rate),
        _fnum(gross),
        _fnum(net),
    )


def parse_klm_group_vs_customer(text):
    rows = []
    party_name = ""
    party_area = ""
    prev_was_band = False

    for raw in text.split("\n"):
        line = raw.rstrip()
        if not line.strip():
            continue

        # ---- customer band -------------------------------------------------
        if _is_band(line):
            if prev_was_band:
                # truncated echo of the previous band -> skip
                continue
            party_name = _band_name(line)
            party_area = ""
            prev_was_band = True
            continue
        prev_was_band = False

        # ---- noise / header / totals --------------------------------------
        if _is_noise(line):
            continue

        # ---- product data row ---------------------------------------------
        parsed = _parse_data_line(line)
        if parsed is None:
            continue
        (item, town, date, bill, batch, mrp, qty, free, rate, gross, net) = parsed

        rows.append(
            [
                party_name,
                town or party_area,
                item,
                date,
                bill,
                batch,
                _fmt(mrp),
                _fmt(qty),
                _fmt(free),
                _fmt(rate),
                _fmt(gross),
                _fmt(net),
            ]
        )

    return H, rows
