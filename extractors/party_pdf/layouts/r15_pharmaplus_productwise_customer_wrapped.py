import io
import re

# ---------------------------------------------------------------------------
# PHARMA + plus (Panjim) — "Product wise sale list for the period ..."
# customer-banded party SALES report whose columns are so narrow that EVERY
# header AND every data value is wrapped across 2-5 physical text lines, so
# pdfplumber's line-based text is unusable (0 rows -> RED "unknown").
#
# Source file:
#   PHARMA PLUS_/Party report/KLM  JUN CUS.xlsx.pdf
#
# The column header, read left-to-right across the wrapped stack, is:
#   Date BillNo Product HSN Pack Batch Ex.Dt. Qty. Free Repl MRP Rate Value
#   P.D.Dis% B.Dis% Scheme Pu.Dis GST S.Value Tr.Rate CGST SGST IGST
#   Customer GSTIN Place
# The first physical header line (whitespace-stripped, lowercased) reads:
#   datbillproducthpabatcex.qty.frere mrratval p.db.schpu.gs.vtr.cgsgsigscustomergsplac
# which is what the gate keys on (see detect_snippet).
#
# LAYOUT (landscape 842x595, ~120 pages, furniture repeats per page):
#   PHARMA + plus                                            <- vendor banner
#   Panjim
#   Product wise sale list for the period 01/06/2026 - ...   <- report title
#   Dat Bill Product H Pa Batc Ex. Qty. Fre Re MR ...        <- wrapped header
#   AAYUU CHEMIST AND DRUGGIST                               <- CUSTOMER band
#   01/ 262 NIOGLOW FACE 34 60 AT3 31/ 1 425 288. 288. ...   <- item row (row 1)
#   06/ 7H  WASH         01 M  502 12/    14  14   ...       <- item row wrap
#   Customer Total ...                                       <- per-party roll-up
#
# Because of the wrapping, this parser is POSITIONAL: it reads word
# x-coordinates from the raw bytes, buckets each word into a fixed column band
# by its x0, then reconstructs every logical record by concatenating the
# fragments of its primary data row (the row that carries BOTH a date at the far
# left AND a Value at x~410) with the wrap rows beneath it — until the next data
# row, Customer/Grand Total, or customer band.
#
# The CUSTOMER name is taken from the product-column band header (which wraps at
# WHOLE-WORD boundaries and is clean, e.g. "AAYUU CHEMIST" / "AND DRUGGIST"),
# NOT from the per-row Customer column at x~716 (which wraps mid-word, e.g.
# "DRUGGIS"+"T"). The band is CARRIED across page breaks (a page can open with
# data rows before the band is reprinted).
#
# Field map (SACRED — qty and value are never mixed; each is its own column):
#   product-col band -> party_name          (carried across pages)
#   Product          -> product_name        (word-wrapped, joined with spaces)
#   Pack             -> pack
#   Batch            -> batch
#   Qty.  (x~267)    -> qty      (sales_qty)
#   Free  (x~300)    -> free     (sales_free)
#   MRP   (x~350)    -> mrp
#   Rate  (x~380)    -> rate
#   Value (x~410)    -> amount   (gross line value, verbatim; NEVER qty*rate)
#   S.Value (x~569)  -> net_amount (kept for cross-check only)
# Only the sales side exists (party sales list); the reconcile is the summed
# Value column vs the printed per-customer "Customer Total" and the file-level
# grand total, which agree to the paise on the reference file.
# ---------------------------------------------------------------------------

# (column_name, x0 band start). A word is assigned to a column when its x0 falls
# in [start - PAD, next_start - PAD).
_COLS = [
    ("date", 21), ("bill", 47), ("product", 73), ("hsn", 166), ("pack", 188),
    ("batch", 210), ("exdt", 240), ("qty", 267), ("free", 300), ("repl", 326),
    ("mrp", 350), ("rate", 380), ("value", 408), ("pd", 437), ("bdis", 465),
    ("scheme", 493), ("pudis", 522), ("gst", 549), ("svalue", 569),
    ("trrate", 599), ("cgst", 629), ("sgst", 657), ("igst", 688),
    ("custcol", 716), ("gstin", 772), ("place", 801),
]
_PAD = 6
# Columns whose fragments are separate whole words -> join with a space.
_SPACED = {"product"}


def _col_of(x0):
    for i, (name, st) in enumerate(_COLS):
        nxt = _COLS[i + 1][1] if i + 1 < len(_COLS) else 10_000
        if st - _PAD <= x0 < nxt - _PAD:
            return name
    return _COLS[-1][0]


def _clean_num(s):
    s = (s or "").strip().replace(",", "")
    if s in ("", "-"):
        return ""
    return s


def _is_primary(ws):
    """A record's FIRST physical row. Everything wraps (date, bill, product,
    MRP, Rate, Value all continue on rows beneath), so a wrap row also carries a
    date-like fragment at x~21 AND MRP/Rate decimal continuations that land in
    those same x-bands. The one column that is present ONLY on the opening row is
    Qty (x~267-306, always printed, '0' when zero); no wrap row ever carries a
    token there. So: date fragment ending in '/' at x~21 AND a Qty token."""
    date_toks = [w["text"] for w in ws if 20 <= w["x0"] <= 26]
    if not (date_toks and date_toks[0].endswith("/")):
        return False
    return any(263 <= w["x0"] <= 307 for w in ws)


def _reconstruct_page(page, carry_party):
    """Return (records, last_party). records is a list of (party, cells) where
    cells maps a column name -> [(top, x0, text), ...]; last_party carries the
    open customer band forward to the next page (a page can open with data rows
    before the band is reprinted)."""
    from collections import defaultdict

    words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
    lines = defaultdict(list)
    for w in words:
        if 150 < w["top"] < 545:  # body region, below the wrapped header stack
            lines[round(w["top"])].append(w)

    records = []
    party = carry_party
    band_parts = []   # accumulate multi-row customer band header
    cur = None        # dict: col -> list[(top, x0, text)]

    def flush_record():
        nonlocal cur
        if cur is not None:
            records.append((party, cur))
            cur = None

    def flush_band():
        nonlocal band_parts, party
        if band_parts:
            party = " ".join(band_parts).strip()
            band_parts = []

    for t in sorted(lines):
        ws = sorted(lines[t], key=lambda w: w["x0"])
        txts = [w["text"] for w in ws]
        joined = " ".join(txts)

        if joined.startswith("Page ") or txts[:1] == ["Dat"]:
            continue
        if joined.startswith("Customer Total") or joined.startswith("Grand Total"):
            flush_band()
            flush_record()
            continue

        if _is_primary(ws):
            flush_band()
            flush_record()
            cur = defaultdict(list)
            for w in ws:
                cur[_col_of(w["x0"])].append((t, w["x0"], w["text"]))
            continue

        has_date = any(20 <= w["x0"] <= 26 for w in ws)
        # a customer band header: no date, every word sits in the PRODUCT-column
        # region (67 <= x0 < 160). The lower bound 67 is essential — it excludes
        # the trailing bill-number wrap fragments "(Cr" / ")" that land at x~47
        # (the Bill column) after a record, which would otherwise be mistaken for
        # a one-word customer band. A band can span several physical rows, so
        # accumulate its fragments.
        if not has_date and ws and all(67 <= w["x0"] < 160 for w in ws):
            flush_record()
            frag = " ".join(txts).strip()
            if frag:
                band_parts.append(frag)
            continue

        # otherwise a wrap-continuation of the current record
        if cur is not None:
            for w in ws:
                cur[_col_of(w["x0"])].append((t, w["x0"], w["text"]))

    flush_band()
    flush_record()
    return records, party


def parse_r15_pharmaplus_productwise_customer_wrapped(text, file_bytes=None):
    H = [
        "Party Name", "Product Name", "Pack", "Batch",
        "Qty", "Free", "MRP", "Rate", "Amount",
    ]
    if not file_bytes:
        return H, []

    import pdfplumber

    rows = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        carry_party = ""
        for page in pdf.pages:
            recs, carry_party = _reconstruct_page(page, carry_party)
            for party, cells in recs:
                def cell(col):
                    items = sorted(cells.get(col, []), key=lambda z: (z[0], z[1]))
                    sep = " " if col in _SPACED else ""
                    return sep.join(x[2] for x in items).strip()

                product = re.sub(r"\s+", " ", cell("product")).strip()
                if not product:
                    continue
                pname = re.sub(r"\s+", " ", (party or "").strip())
                rows.append([
                    pname,
                    product,
                    cell("pack"),
                    cell("batch"),
                    _clean_num(cell("qty")),
                    _clean_num(cell("free")),
                    _clean_num(cell("mrp")),
                    _clean_num(cell("rate")),
                    _clean_num(cell("value")),
                ])
    return H, rows
