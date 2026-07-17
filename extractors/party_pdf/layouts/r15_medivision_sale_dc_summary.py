import re

# ---------------------------------------------------------------------------
# MediVision "Platinum" party layout: "Customer-wise, product-wise sale/DC
# summary"  (RAJU PHARMA, PARBHANI -- KLM Laboratories distributor).
# Source: RAJU PHARMA PARBHANI/Party report/klm may 26 report.pdf
#
# This is the *summary* sibling of medivision_sale_dc (which is the "sale/DC
# details" report -- that one carries voucher / batch / expiry / MRP columns and
# is parsed by extractors/party_pdf/layouts/medivision_sale_dc.py). The summary
# report collapses each party-product to a single line with only:
#     Particulars | Addr/unit | Co | Qty | Scm qty | Scm disc | Item disc | Amount
#
# Exact column-header gate token (whitespace-stripped, lowercased) -- taken from
# the report title, which is unique across the corpus and does NOT collide with
# the "details" variant ("...sale/dcdetails"):
#     customer-wise,product-wisesale/dcsummary
#
# CRITICAL: like every MediVision PDF, the glyphs are an Adobe UTF-8 CID font
# that pdfplumber / pdfminer cannot decode; PyMuPDF (fitz) decodes them.  This
# layout is therefore parsed POSITIONALLY from ``page.get_text("words")``,
# bucketing each word into its column by x0.  Column x0 windows (from the header
# row; numbers are right-aligned, names/pack left-aligned; page width ~595):
#     Particulars (name)   x0  14 (party band) / 18 (product row, indented)
#     Addr/unit            x0 ~156-220  (party -> town ; product -> pack)
#     Co  (== "*KL")       x0 ~227      (product rows ONLY -- the discriminator)
#     Qty                  x0 ~295-304  (right-aligned)
#     Scm qty  (free)      x0 ~355-385
#     Scm disc / Item disc x0 ~390-500  (always blank in this report)
#     Amount               x0 ~520-560  (right-aligned)
#
# Row shapes:
#   PARTY BAND (name flush-left x0<30, NO "*KL" at x~227, town in Addr/unit):
#       <PARTY NAME x0<150>  <TOWN x0 155-220>  <QTY-total>  [<FREE-total>]  <AMOUNT-total>
#     e.g.  "ABHIRA MED STORES  JINTUR  40  16  4000.00"
#   PRODUCT ROW (name indented x0~18, HAS "*KL" at x~227, pack in Addr/unit):
#       <PRODUCT NAME x0<150>  <PACK x0 155-220>  *KL  <QTY>  [<FREE>]  <AMOUNT>
#     e.g.  "CUTIHEAL CREAM 15GM  1*15GM  *KL  20  12  2500.00"
#
# Field map (SACRED -- qty and value are never mixed):
#     party_name  = band name          (Particulars, party band)
#     area        = band town          (Addr/unit,  party band)
#     product_name= product name       (Particulars, product row)
#     pack        = product pack/unit  (Addr/unit,  product row)
#     qty         = Qty      -> sales_qty
#     free_qty    = Scm qty  -> sales_free (scheme / DC free goods)
#     amount      = Amount   -> sales_value
# The "Scm disc"/"Item disc" columns are empty throughout and are NOT emitted, so
# no discount value ever lands on a quantity slot.  Party sales summary -> only
# the sales side exists; reconcile is qty & amount vs the printed per-party band
# totals (each band's product rows sum to its printed Qty / Scm-qty / Amount, and
# the summed grand total matches the printed "Totals:", e.g. 692759.69).
# ---------------------------------------------------------------------------

H = ["Party Name", "Area", "Product Name", "Pack", "Qty", "Free", "Amount"]

_INT = re.compile(r"^\d+$")
_DEC = re.compile(r"^[\d,]+\.\d+$")

# Column x0 windows.
_QTY_LO, _QTY_HI = 285, 320
_FREE_LO, _FREE_HI = 350, 388
_AMT_LO, _AMT_HI = 518, 562
_CO_LO, _CO_HI = 222, 240          # "*KL" -- present only on product rows
_NAME_MAX_X = 150                  # name ends before the Addr/unit column
_UNIT_LO, _UNIT_HI = 152, 222      # Addr/unit column (town OR pack)
_BAND_MAX_X = 30                   # party band name starts flush-left


def _tok(ws, lo, hi, pat):
    """First word whose x0 is in [lo, hi) and text matches ``pat``; else None."""
    for w in ws:
        if lo <= w[0] < hi and pat.match(w[4]):
            return w[4]
    return None


def _num(t):
    try:
        return float(t.replace(",", ""))
    except (ValueError, AttributeError):
        return 0.0


def parse_r15_medivision_sale_dc_summary(text, file_bytes=None):
    if not file_bytes:
        return H, []

    import fitz  # PyMuPDF -- required; pdfplumber cannot read this CID font

    rows = []
    party_name = ""
    area = ""
    have_party = False

    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        for page in doc:
            words = page.get_text("words")  # (x0, y0, x1, y1, text, blk, ln, wd)
            if not words:
                continue
            words.sort(key=lambda w: (round(w[1]), w[0]))
            lines = {}
            for w in words:
                lines.setdefault(round(w[1]), []).append(w)

            for y in sorted(lines):
                ws = sorted(lines[y], key=lambda w: w[0])
                # skip the lone "MediVision" watermark line
                if len(ws) == 1 and ws[0][4] == "MediVision":
                    continue

                # a product row carries the company code "*KL" at x~227
                has_co = any(_CO_LO <= w[0] < _CO_HI and w[4].startswith("*K")
                             for w in ws)

                # ---- PRODUCT ROW -----------------------------------------
                if has_co:
                    if not have_party:
                        continue
                    # product name = words left of the Addr/unit column, minus
                    # any stray "MediVision" watermark that overlaps the row
                    name = " ".join(
                        w[4] for w in ws
                        if w[0] < _NAME_MAX_X and w[4] != "MediVision"
                    ).strip()
                    pack = _tok(ws, _UNIT_LO, _UNIT_HI,
                                re.compile(r"^\S+$")) or ""
                    qty = _num(_tok(ws, _QTY_LO, _QTY_HI, _INT) or "0")
                    free = _num(_tok(ws, _FREE_LO, _FREE_HI, _INT) or "0")
                    amt = _num(_tok(ws, _AMT_LO, _AMT_HI, _DEC) or "0")
                    if not name:
                        continue
                    rows.append([
                        party_name, area, name, pack,
                        "%g" % qty, "%g" % free, "%.2f" % amt,
                    ])
                    continue

                # ---- PARTY BAND: flush-left, no "*KL" --------------------
                if ws[0][0] < _BAND_MAX_X:
                    qty_tok = _tok(ws, _QTY_LO, _QTY_HI, _INT)
                    free_tok = _tok(ws, _FREE_LO, _FREE_HI, _INT)
                    amt_tok = _tok(ws, _AMT_LO, _AMT_HI, _DEC)
                    # page furniture (title / "Particulars" header / "Totals:")
                    # carries no per-party total in these columns
                    if qty_tok is None and free_tok is None and amt_tok is None:
                        continue
                    name = " ".join(
                        w[4] for w in ws
                        if w[0] < _NAME_MAX_X and w[4] != "MediVision"
                    ).strip()
                    if not name:
                        continue
                    # drop the "Totals:" grand-total footer band
                    if name.lower().startswith("totals"):
                        continue
                    town = " ".join(
                        w[4] for w in ws if _UNIT_LO <= w[0] < _UNIT_HI
                    ).strip()
                    party_name = name
                    area = town
                    have_party = True

    return H, rows
