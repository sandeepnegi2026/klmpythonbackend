import re

# PURUSHOTHAM MEDICAL AGENCIES "Area Wise Customer, Company And Product Sales"
# (PROFITMAKER / Daxinsoft Technologies party report, KLM division).
#
# GATE TOKEN (compact header run, unique):  productnameqtyfreegrossnetamount
# (paired with title token  areawisecustomer,companyandproductsales)
#
# Structure (single physical line per product):
#   PURUSHOTHAM MEDICAL AGENCIES
#   Area Wise Customer, Company And Product Sales
#   From 01/05/2026 To 31/05/2026        Page : 1
#   COMPANY :KLM(COSMO)
#   Product Name QTY FREE Gross Net Amount      <- fixed column header (repeats/page)
#   Customer :<NAME>  CITY:<AREA>               <- party band (area after "CITY:")
#   <PRODUCT NAME> <Qty> [<Free>] <Gross> <NetAmount>   <- single-line rows
#   ...
#   Total: <qty> [<free>] <gross> <netamount>   <- per-band footer (skipped)
#   Grand Total : ...                           <- footer (skipped)
#
# NOISE: every page carries a giant diagonal watermark spelling the vendor name,
# rendered as single huge-font (height ~90-105pt) glyphs scattered across the page.
# These land as stray single-letter "words" (e.g. a lone "H"/"T"/"D" line) AND, worse,
# merge INTO real tokens on the same baseline -> "542.1A6" (=542.16), "928D.55"
# (=928.55), "TotUal:" (=Total:), "2384.75A". Body text is height ~8pt.
#
# We parse POSITIONALLY off word x-coordinates (needs file_bytes) because the header
# columns are fixed:  QTY@107  FREE@145  Gross@203  Net Amount@256/275. Numeric
# buckets are stripped of every non-[0-9.] char (removes any embedded watermark
# letter and keeps the true number's x-position intact). Product name = words with
# x0 < 100 that are NOT huge-font watermark glyphs.
#
# COLUMN MAPPING (sacred: qty stays qty, value stays value):
#   Qty    <- QTY column         (integer sale qty)
#   Free   <- FREE column        (scheme qty, only sometimes printed)
#   Amount <- GROSS column       (the real sales value; per-row Gross == NetAmount*100
#             exactly for every row, i.e. the vendor's tiny "Net Amount" column is a
#             /100-scaled display artifact. Gross reconciles to the Grand Total.)
# Verified reconcile on the sample: qty sum 984.00, free 18.00, gross 184480.99 --
# byte-exact to the printed "Grand Total : 984.00  18.00  184480.99".

_BAND = re.compile(r'Customer\s*:\s*(?P<party>.+?)\s+CITY\s*:\s*(?P<area>.*)$', re.I)
_FOOTER = re.compile(r'^(tot.?al|grand)')          # 'total', watermark-merged 'totual'
_NOISE = re.compile(
    r'(?i)^\s*(Product\s+Name|From\s|COMPANY\s*:|Area\s+Wise|Page\s*:'
    r'|Generated|PURUSHOTHAM)'
)


def _num(tok):
    """Keep only digits and dot -> strips any embedded/adjacent watermark letter."""
    return re.sub(r'[^0-9.]', '', tok)


def _alpha(tok):
    return re.sub(r'[^a-z]', '', tok.lower())


def parse_profitmaker_area_customer_company_product(text, file_bytes=None):
    headers = ["Party Name", "Area", "Product Name", "Qty", "Free", "Amount"]
    rows = []
    if not file_bytes:
        return headers, rows

    import io
    import pdfplumber

    party = ""
    area = ""
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            if not words:
                continue
            # cluster words into physical lines by baseline (top)
            words.sort(key=lambda w: (round(w["top"] / 2), w["x0"]))
            lines = []
            cur = []
            ctop = None
            for w in words:
                if ctop is None or abs(w["top"] - ctop) <= 4:
                    cur.append(w)
                    ctop = w["top"] if ctop is None else ctop
                else:
                    lines.append(cur)
                    cur = [w]
                    ctop = w["top"]
            if cur:
                lines.append(cur)

            for ln in lines:
                sw = sorted(ln, key=lambda w: w["x0"])
                joined = " ".join(w["text"] for w in sw).strip()

                m = _BAND.search(joined)
                if m:
                    party = m.group("party").strip()
                    area = m.group("area").strip()
                    continue

                first_alpha = _alpha(sw[0]["text"]) if sw else ""
                if _FOOTER.match(first_alpha):
                    continue
                if _NOISE.match(joined):
                    continue
                if not party:
                    continue

                prod = []
                qty = free = gross = ""
                for w in sw:
                    x = w["x0"]
                    t = w["text"]
                    tall = (w["bottom"] - w["top"]) >= 40  # watermark glyph
                    if x < 100:
                        if not tall:
                            prod.append(t)
                    elif x < 143:
                        qty = _num(t) or qty
                    elif x < 190:
                        free = _num(t) or free
                    elif x < 250:
                        gross = _num(t) or gross
                    # x >= 250 is the /100 "Net Amount" artifact column -> ignored

                product = " ".join(prod).strip()
                if not product or not qty:
                    continue
                rows.append([party, area, product, qty, free, gross])

    return headers, rows
