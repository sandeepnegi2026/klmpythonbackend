import io
import re

# ---------------------------------------------------------------------------
# SREE SUPREME PHARMA (NAMAKKAL) — KLM LAB / CASMO-family DOS-printer exports.
# Two sibling "billwise" party reports from the same ERP, both positional
# (monospace text layer, columns fixed by x-coordinate). Handled here as two
# parse functions sharing the same numeric-tail logic.
#
#   Variant 1  "PROD/CUST.WISE SALES"   (files A-KLM-1 .. A-KLM-7)
#       PRODUCT band -> invoice rows
#       INV.NO INV.DATE CUSTOMER NAME PLACE QTY FREE REPL RATE VALUE
#       party = CUSTOMER NAME,  area = PLACE,  product = current band.
#
#   Variant 2  "AREA-PROD-WISE SALES"   (file KLM-AREA1-300626)
#       AREA band -> CUSTOMER band -> product-led rows
#       PRODUCT NAME PACKG INV.NO INV.DATE QTY FREE REPL VALUE
#       party = CUSTOMER band, area = AREA band, product = leading text.
#
# In both, a "row" is one printed invoice line. Sale lines carry RATE+VALUE
# (two 2-decimal money tokens); free/scheme lines carry only an integer in the
# FREE/REPL column and no money. VALUE maps to "Amount".
# ---------------------------------------------------------------------------

# A DD/MM/YY invoice date — the structural anchor separating the id/name block
# from the numeric block in both variants.
_DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{2}$")
# A money token: 2 decimal places, optional thousands commas, optional sign.
_MONEY_RE = re.compile(r"^-?\d[\d,]*\.\d{2}$")
# A bare integer (qty / free / repl), optional sign.
_INT_RE = re.compile(r"^-?\d+$")


def _num(tok):
    return tok.replace(",", "")


def _is_separator(joined):
    """Dash / asterisk rule lines and blank lines."""
    return not joined or bool(re.fullmatch(r"[-*=_\s]+", joined))


def _is_furniture(joined):
    low = joined.lower()
    if _is_separator(joined):
        return True
    if low.startswith("page no") or "dosprinter" in low or "end of list" in low:
        return True
    if "sree supreme pharma" in low or low.startswith("company:") or low.startswith("comp:"):
        return True
    if "prod/cust.wise" in low or "area-prod-wise" in low:
        return True
    if low.startswith("inv.no") or low.startswith("product name"):
        return True
    # footer totals block
    if low.startswith(("trade disc", "net sales", "expiry/damage")):
        return True
    if low.startswith("area total"):
        return True
    return False


def _split_numeric_tail(numwords):
    """Given the trailing numeric words of a row (already filtered to x in the
    numeric band), classify them into (qty, free, amount).

    Rule (unambiguous over the observed corpus):
      * money tokens (2 decimals) are RATE then VALUE -> amount = last money;
        the integers to their left are qty, free, repl in that column order.
      * no money token -> a free/scheme-only line: the trailing integer is the
        FREE qty (qty=0, amount=0).
    """
    money = [w for w in numwords if _MONEY_RE.match(w)]
    ints = [w for w in numwords if _INT_RE.match(w)]
    if money:
        amount = _num(money[-1])
        qty = _num(ints[0]) if len(ints) >= 1 else "0"
        free = _num(ints[1]) if len(ints) >= 2 else "0"
        return qty, free, amount
    # free-only line
    free = _num(ints[-1]) if ints else "0"
    return "0", free, "0.00"


# ===========================================================================
# Variant 1 — PROD/CUST.WISE SALES  (positional)
# ===========================================================================
# Column x-boundaries observed (header: INV.NO@43 INV.DATE@81 CUSTOMER@127
# NAME@170 PLACE@207 QTY@263 FREE@287 REPL@315 RATE@347 VALUE@394):
_V1_NAME_X0 = 120     # customer name starts ~127
_V1_PLACE_X0 = 205    # place column starts ~207
_V1_NUM_X0 = 258      # first numeric column (QTY) starts ~263


def parse_prodcust_wise_billwise(text, file_bytes=None):
    """SREE SUPREME PHARMA 'PROD/CUST.WISE SALES' (KLM CASMO-family).

    PRODUCT band -> invoice rows. Positional: word x0 slices
    inv/date | name | place | numeric-tail; the flat text glues name+place and
    multi-word places ("ATC BACK") so a positional split is required.
    """
    headers = [
        "Product Name", "Invoice No", "Invoice Date",
        "Party Name", "Area", "Qty", "Free", "Amount",
    ]
    if not file_bytes:
        return headers, []

    import pdfplumber

    rows = []
    product = ""
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            linemap = {}
            for w in page.extract_words():
                linemap.setdefault(round(w["top"]), []).append(w)
            for top in sorted(linemap):
                ws = sorted(linemap[top], key=lambda w: w["x0"])
                joined = " ".join(w["text"] for w in ws)
                if _is_furniture(joined):
                    continue

                # a data row begins with INV.NO then a DD/MM/YY date
                is_data = (
                    len(ws) >= 2
                    and ws[0]["text"].isdigit()
                    and _DATE_RE.match(ws[1]["text"])
                )
                if is_data:
                    inv_no = ws[0]["text"]
                    inv_date = ws[1]["text"]
                    name = " ".join(
                        w["text"] for w in ws
                        if _V1_NAME_X0 <= w["x0"] < _V1_PLACE_X0
                    ).strip().rstrip(",")
                    place = " ".join(
                        w["text"] for w in ws
                        if _V1_PLACE_X0 <= w["x0"] < _V1_NUM_X0
                    ).strip()
                    numwords = [w["text"] for w in ws if w["x0"] >= _V1_NUM_X0]
                    if not name:
                        continue
                    qty, free, amount = _split_numeric_tail(numwords)
                    rows.append([product, inv_no, inv_date, name, place, qty, free, amount])
                    continue

                # a product-subtotal line: bare numbers, no leading inv-no/date.
                nums = [w["text"] for w in ws]
                if all(_MONEY_RE.match(t) or _INT_RE.match(t) for t in nums):
                    continue  # subtotal / roll-up — skip

                # otherwise: a PRODUCT band (heading text).
                if re.search(r"[A-Za-z]", joined):
                    product = joined.strip()
    return headers, rows


# ===========================================================================
# Variant 2 — AREA-PROD-WISE SALES  (positional)
# ===========================================================================
# Header: PRODUCT@43 NAME@81 PACKG@141 INV.NO@174 INV.DATE@212 QTY@268
#         FREE@291 REPL@319 VALUE@375
_V2_NUM_X0 = 258      # numeric columns (QTY..VALUE) start ~268


def parse_areaprod_wise_billwise(text, file_bytes=None):
    """SREE SUPREME PHARMA 'AREA-PROD-WISE SALES' (KLM CASMO-family).

    AREA band -> CUSTOMER band -> product-led invoice rows. Each data row is
    'PRODUCT NAME PACKG INV.NO INV.DATE QTY [VALUE]'. The invoice number is the
    all-digit token immediately preceding the DD/MM/YY date; everything before
    it is the product+pack; everything after is the numeric tail.
    """
    headers = [
        "Product Name", "Invoice No", "Invoice Date",
        "Party Name", "Area", "Qty", "Free", "Amount",
    ]
    if not file_bytes:
        return headers, []

    import pdfplumber

    rows = []
    area = ""
    customer = ""
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            linemap = {}
            for w in page.extract_words():
                linemap.setdefault(round(w["top"]), []).append(w)
            for top in sorted(linemap):
                ws = sorted(linemap[top], key=lambda w: w["x0"])
                toks = [w["text"] for w in ws]
                joined = " ".join(toks)
                if _is_furniture(joined):
                    continue

                # locate an INV.NO (all-digit) directly followed by a DD/MM/YY date
                date_i = next(
                    (
                        i for i in range(1, len(toks))
                        if _DATE_RE.match(toks[i]) and toks[i - 1].isdigit()
                    ),
                    None,
                )
                if date_i is not None:
                    inv_no = toks[date_i - 1]
                    inv_date = toks[date_i]
                    product = " ".join(toks[: date_i - 1]).strip()
                    numwords = [
                        w["text"] for w in ws
                        if w["x0"] >= _V2_NUM_X0 and (
                            _MONEY_RE.match(w["text"]) or _INT_RE.match(w["text"])
                        )
                    ]
                    qty, free, amount = _split_numeric_tail(numwords)
                    rows.append(
                        [product, inv_no, inv_date, customer, area, qty, free, amount]
                    )
                    continue

                # a customer sub-total: a lone money token -> skip
                if len(toks) == 1 and _MONEY_RE.match(toks[0]):
                    continue

                # band lines: AREA (single token, no comma) vs CUSTOMER (has comma
                # or multiple words). The customer heading always carries a comma
                # ("DR.SARANYA.C.MBBS,DDVL, RASIPURAM-637408" / "VANITHA PHARMACY,
                # NAMAKKAL-637001"); the area heading is a bare place token.
                if "," in joined:
                    customer = joined.strip()
                elif re.search(r"[A-Za-z]", joined):
                    area = joined.strip()
                    customer = ""   # new area resets the pending customer
    return headers, rows
