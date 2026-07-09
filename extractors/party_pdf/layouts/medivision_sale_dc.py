import io
import re

# ---------------------------------------------------------------------------
# SIND DISTRIBUTORS "MediVision Platinum" party layout:
#   "Customer-wise, product-wise sale/DC details"
#
# Title / furniture (repeated every page):
#   MediVision (watermark) | SIND DISTRIBUTORS | address | Phone/Mobile | Email |
#   "Customer-wise, product-wise sale/DC details" | "KLM L, KLM L, ..." |
#   "01-05-26 to 31-05-26" | "Page No. N" | the Particulars column header row |
#   footer "Continued..." / "Totals:" grand total.
#
# CRITICAL: these PDFs are produced by MediVision with an Adobe UTF-8 CID font
# layer that pdfplumber / pdfminer CANNOT decode (they yield empty / garbage
# glyphs). PyMuPDF (fitz) decodes them correctly, so this layout is parsed
# POSITIONALLY from ``page.get_text("words")``, bucketing every word into its
# column by x0 (numbers are right-aligned, names/pack are left-aligned).
#
# Row shapes (page width ~595):
#   PARTY BAND (flush-left, x0~28, NO voucher/batch):
#     <PARTY NAME tokens x0<90> [ "(" ] <ROUTE code x0~96> <QTY@~247-252>
#         [<FREE@~292>] <AMOUNT@~533-538>
#     e.g. "AASRA NAR 79 9187.10"  -> party_name="AASRA", route="NAR",
#          qty-total 79, amount-total 9187.10 (its product rows reconcile to it)
#   PRODUCT ROW (indented, has a voucher SD/... @x~182 AND an Exp dd-mm @x~409):
#     <PRODUCT NAME x0<90 (may be blank / multi-word)> <PACK@~96> <KL@~123>
#       <vch-date@~141> <SD/nnnn@~182> <QTY@~252> [<FREE@~292>] <BATCH@~345>
#       <EXP dd-mm@~409> <MRP@~488> <AMOUNT@~538>
#     e.g. DESOSOFT 10 KL 25-05-2 SD/1526 2 BJ602 02-28 140.63 214.30
#
# "sale/DC" = a party may carry free-goods (DC / scm) rows with a qty in the
# FREE column and no sale value; such a band prints only a free-qty total (no
# amount), so the band detector accepts qty OR free OR amount.
#
# MAPPING: party_name = band name (route code + '(' stripped); product_name;
# pack; batch; expiry; MRP (=rate/list price); Qty (=sales); Free (=sales_free,
# scm/free qty, 0 if empty); Amount (=sales_value, net line value).
#
# Reconciles EXACTLY on both reference files (report.pdf 330 parties / 1453
# rows, report-2.pdf 326 parties / 1424 rows): every band's product rows sum to
# the printed per-party qty / free / amount totals, and the summed grand total
# matches the printed "Totals:" (e.g. report.pdf 721425.10; AASRA qty 79 /
# amount 9187.10).
# ---------------------------------------------------------------------------

H = ["Party Name", "Route", "Product Name", "Pack", "Batch", "Expiry",
     "MRP", "Qty", "Free", "Amount", "Vch Date", "Vch No"]

_INT = re.compile(r"^\d+$")
_DEC = re.compile(r"^[\d,]+\.\d+$")
_VCH = re.compile(r"^[A-Z]{1,4}/\S+$")      # voucher e.g. SD/1526
_EXP = re.compile(r"^\d\d-\d\d$")           # expiry mm-yy e.g. 02-28
# voucher date, clipped by MediVision's narrow column to dd-mm-<1 digit>; the
# full 2-digit year is recovered from the report-period header.
_VDATE = re.compile(r"^(\d\d-\d\d)-\d")

# Column x0 windows (numbers are right-aligned; qty single-digit lands ~252,
# two-digit ~247; free ~281-292; amount ~521-543).
_QTY_LO, _QTY_HI = 238, 272
_FREE_LO, _FREE_HI = 272, 305
_MRP_LO, _MRP_HI = 470, 505
_AMT_LO, _AMT_HI = 515, 550
_NAME_MAX_X = 90                            # party / product name ends before pack
_PACK_LO, _PACK_HI = 90, 116
_ROUTE_LO, _ROUTE_HI = 90, 130
_BAND_MAX_X = 32                            # band starts flush-left
_BATCH_LO, _BATCH_HI = 340, 405
_EXP_LO, _EXP_HI = 400, 470


def _tok(ws, lo, hi, pat):
    """First word whose x0 is in [lo, hi) and text matches `pat`; else None."""
    for w in ws:
        if lo <= w[0] < hi and pat.match(w[4]):
            return w[4]
    return None


def _num(t):
    try:
        return float(t.replace(",", ""))
    except (ValueError, AttributeError):
        return 0.0


def parse_medivision_sale_dc(text, file_bytes=None):
    if not file_bytes:
        return H, []

    import fitz  # PyMuPDF — required; pdfplumber cannot read this CID font

    # report-period year (e.g. "01-05-26 to 31-05-26" -> "26") to restore the
    # year clipped off each row's voucher date
    ym = re.search(r"\d\d-\d\d-(\d\d)\s*to\s*\d\d-\d\d-\d\d", text or "")
    doc_yy = ym.group(1) if ym else ""

    rows = []
    party_name = ""       # current band's cleaned party name
    route = ""            # current band's route code
    have_party = False

    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        for page in doc:
            words = page.get_text("words")  # (x0, y0, x1, y1, text, blk, ln, wd)
            if not words:
                continue
            # cluster words into visual rows by baseline (y0 within tolerance)
            words.sort(key=lambda w: (round(w[1]), w[0]))
            lines = {}
            for w in words:
                lines.setdefault(round(w[1]), []).append(w)

            for y in sorted(lines):
                ws = sorted(lines[y], key=lambda w: w[0])
                # skip the lone "MediVision" watermark line
                if len(ws) == 1 and ws[0][4] == "MediVision":
                    continue

                has_vch = any(178 <= w[0] <= 205 and _VCH.match(w[4]) for w in ws)
                has_exp = any(_EXP_LO <= w[0] <= _EXP_HI and _EXP.match(w[4]) for w in ws)

                # ---- PRODUCT ROW: carries a voucher AND an expiry ----------
                if has_vch and has_exp:
                    if not have_party:
                        continue
                    name = " ".join(w[4] for w in ws if w[0] < _NAME_MAX_X).strip()
                    pack = _tok(ws, _PACK_LO, _PACK_HI, re.compile(r"^\S+$")) or ""
                    qty = _num(_tok(ws, _QTY_LO, _QTY_HI, _INT) or "0")
                    free = _num(_tok(ws, _FREE_LO, _FREE_HI, _INT) or "0")
                    batch = _tok(ws, _BATCH_LO, _BATCH_HI, re.compile(r"^\S+$")) or ""
                    exp = _tok(ws, _EXP_LO, _EXP_HI, _EXP) or ""
                    mrp = _num(_tok(ws, _MRP_LO, _MRP_HI, _DEC) or "0")
                    amt = _num(_tok(ws, _AMT_LO, _AMT_HI, _DEC) or "0")
                    # voucher no. (SD/nnnn @x~182) + its date (@x~141) — the fields
                    # that distinguish two same-product/batch line items on different
                    # invoices (without them such rows collapse to false duplicates)
                    vch_no = _tok(ws, 178, 210, _VCH) or ""
                    vd = _tok(ws, 128, 178, _VDATE)
                    vch_date = ""
                    if vd:
                        dm = _VDATE.match(vd).group(1)
                        vch_date = f"{dm}-{doc_yy}" if doc_yy else dm
                    rows.append([
                        party_name, route, name, pack, batch, exp,
                        "%.2f" % mrp, "%g" % qty, "%g" % free, "%.2f" % amt,
                        vch_date, vch_no,
                    ])
                    continue

                # ---- PARTY BAND: flush-left, no voucher/expiry -------------
                if ws[0][0] < _BAND_MAX_X:
                    qty_tok = _tok(ws, _QTY_LO, _QTY_HI, _INT)
                    free_tok = _tok(ws, _FREE_LO, _FREE_HI, _INT)
                    amt_tok = _tok(ws, _AMT_LO, _AMT_HI, _DEC)
                    # page furniture (e.g. "SIND DISTRIBUTORS") carries no totals
                    if qty_tok is None and free_tok is None and amt_tok is None:
                        continue
                    name = " ".join(
                        w[4] for w in ws if w[0] < _NAME_MAX_X
                    ).strip()
                    # drop the route-opening '(' — standalone ("AAI MEDICAL (")
                    # or glued to the last name token ("LIFE MEDICAL(")
                    name = name.rstrip(" (").strip()
                    if not name:
                        continue
                    party_name = name
                    # route = every non-numeric token in the route window, minus a
                    # bare '(' (handles multi-token routes like "V M"; empty if none)
                    route = " ".join(
                        w[4] for w in ws
                        if _ROUTE_LO <= w[0] < _ROUTE_HI
                        and not _DEC.match(w[4]) and not _INT.match(w[4])
                        and w[4] != "("
                    ).strip()
                    have_party = True

    return H, rows
