"""M.M.TRADERS 'Stock And Sales Report(Month)' — KLM LABORATORIES 31-column
full-word dialect (x-coordinate positional parser).

Vendor:  M.M.TRADERS (KLM LABORATORIES PVT. LTD; one wide report, no per-division
         sections). Title line: 'Stock And Sales Report(Month) of <Mon><Year> for
         KLM LABORATORIES PVT. LTD'.

Why a dedicated positional parser (NOT the simple4 / generic fallback and NOT any
existing klm_stock_sales_month sibling):

  * This is a VERY wide 31-numeric-column export whose full-word column header
    ('ProductName Pack OpeningStock ... Purch(ase)Quantity SaleValue TotalStock
    ILastSalesVal OpeningStockFree Purchase(Value) SaleQuantity ILastNetVa ... Sale
    SaleV ... ILastSalesQty ... ItemCost ...') is printed in TWO vertically stacked
    header text-layers that pdfplumber renders GLYPH-INTERLEAVED, AND the first
    product row (BLEMGUARD FACE SERUM) is printed at the SAME vertical position as the
    header, so the flat text of the header line and the first data row are physically
    scrambled together ('...PackOpeningStock2Purchnatistyequa2SaleValue848.28...').
    The header token order therefore cannot be read; the generic/simple4 fallback
    pops the LAST N numbers per line and mis-assigns columns -> ~96% false
    SANITY_FAILED on the stock_pdf 'generic' route.

  * The 31 numeric columns are RIGHT-aligned and stable across every data row, so we
    recover the column layout POSITIONALLY: cluster the right edges (x1) of all
    numeric tokens in the data band into 31 columns, then read fields by ORDINAL
    column index (which is fixed by the KLM template):
        col0  = OpeningStock (opening qty)
        col1  = Purchase     (purchase qty)
        col3  = SaleQuantity (sales qty)
        col7  = TotalStock   (closing qty)
    Vendor identity holds EXACTLY on 144/145 clean rows:
        CLOSING(col7) = OPENING(col0) + PURCHASE(col1) - SALES(col3)
    e.g.  DESOSOFT CREAM 10 GM   op7  pur15 sale6  -> close16 (7+15-6=16)  OK
          COSMOQ SHAMPOO 200 ML  op5  pur0  sale2  -> close3  (5+0-2=3)    OK
          COSMO Q CONDITIONER    op1  pur3  sale4  -> close0  (1+3-4=0)    OK
    (the single non-reconciling row, 'KLM D3 NANO DROP', is itself glyph-corrupted in
    the source text layer — several of its cells are dropped/merged by pdfplumber — so
    it is a rendering defect, not a column mis-read.)

  The other 27 columns are per-column value / prev-month / free / return / cost stats
  whose header labels are scrambled beyond safe recovery; since they are ALL zero for
  free/return in this export and the QTY identity fully reconciles on col0/1/3/7, we
  map only the four confirmed quantity columns and never guess a value column
  (SACRED RULE: never derive a quantity from a value, never fabricate a mapping).

Product / Pack split by x-band: name tokens have center < 135pt; the Pack cell (when
present) sits in the 135-165pt band; numeric data starts at ~190pt.

Detect gate (compact, spaces-stripped, lowercased): title 'stockandsalesreport(month)'
AND the full-word header tokens 'packopeningstock' AND 'salequantity' AND
'ilastsalesqty' — this trio is unique to this 31-column full-word dialect and is
DISJOINT from every existing klm_stock_sales_month sibling token
(opstpursalefreeadjcl.s / op.qtpurchfree+tot.ssale_val / opstpurq+repqsalevalue /
openingpureilast+netstock+@pur), so it cannot steal any of them. Place it just BEFORE
the klm_stock_sales_month sibling gates (the 'stockandsalesreport(month)' block).
"""
import io
import re

_NAME_CUT = 135.0   # product-name tokens have center left of this
_PACK_MAX = 165.0   # pack cell lives in the 135-165pt band
_DATA_MIN = 190.0   # numeric data columns start here
_CLUS_GAP = 6.0     # x1 within this many points -> same column
_MIN_SUPPORT = 8    # a real column has at least this many numeric tokens
_TOL = 6.0          # bind a token to a column center within this window

# ordinal column indices (fixed by the KLM 31-column template)
_C_OPENING = 0
_C_PURCHASE = 1
_C_SALES = 3
_C_CLOSING = 7


def _is_num(t):
    t = t.replace(",", "")
    if not t:
        return False
    try:
        float(t)
        return True
    except ValueError:
        return False


def _to_f(t):
    try:
        return float(t.replace(",", ""))
    except ValueError:
        return 0.0


def _row_words(page):
    words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
    by_top = {}
    for w in words:
        by_top.setdefault(round(w["top"]), []).append(w)
    return [sorted(by_top[t], key=lambda w: w["x0"]) for t in sorted(by_top)]


def parse_r15_klm_ss_month_totalstock_ilast_positional(text, file_bytes=None):
    if not file_bytes:
        return []
    import pdfplumber

    records = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        pages_rows = [_row_words(p) for p in pdf.pages]

        # Pass 1: derive the 31 column right-edge (x1) centers from all numeric tokens
        # in the data band, across every page (columns are shared).
        xs = []
        for rows in pages_rows:
            for rw in rows:
                for w in rw:
                    cx = (w["x0"] + w["x1"]) / 2.0
                    if cx >= _DATA_MIN and _is_num(w["text"]):
                        xs.append(w["x1"])
        if not xs:
            return []
        xs.sort()
        clusters = []
        for x in xs:
            if clusters and x - clusters[-1][-1] < _CLUS_GAP:
                clusters[-1].append(x)
            else:
                clusters.append([x])
        centers = [sum(c) / len(c) for c in clusters if len(c) >= _MIN_SUPPORT]
        # need enough columns to reach the closing column
        if len(centers) <= _C_CLOSING:
            return []

        def col_of(x1):
            best, bd = None, _TOL
            for i, c in enumerate(centers):
                d = abs(x1 - c)
                if d < bd:
                    bd = d
                    best = i
            return best

        # Pass 2: emit product rows
        for rows in pages_rows:
            for rw in rows:
                name_tokens, pack_tokens = [], []
                col_tokens = []
                for w in rw:
                    cx = (w["x0"] + w["x1"]) / 2.0
                    if cx < _NAME_CUT:
                        name_tokens.append(w)
                    elif cx < _PACK_MAX:
                        pack_tokens.append(w)
                    else:
                        col_tokens.append(w)

                name = re.sub(r"\s+", " ", " ".join(w["text"] for w in name_tokens)).strip()
                if not name or not re.search(r"[A-Za-z]", name):
                    continue
                low = name.lower()
                # header / banner / title lines
                if low.startswith(("m.m.trader", "stock and sales", "report generated",
                                   "productname", "product name")):
                    continue
                # the header line's product-name column reads 'ProductName ...' fragments;
                # a genuine product row must carry numeric data cells
                vals = {}
                for w in col_tokens:
                    t = w["text"]
                    if not _is_num(t):
                        continue
                    ci = col_of(w["x1"])
                    if ci is None:
                        continue
                    vals.setdefault(ci, _to_f(t))
                if _C_CLOSING not in vals and _C_OPENING not in vals:
                    continue

                opening = vals.get(_C_OPENING, 0.0)
                purchase = vals.get(_C_PURCHASE, 0.0)
                sales = vals.get(_C_SALES, 0.0)
                closing = vals.get(_C_CLOSING, 0.0)

                pack = re.sub(r"\s+", " ",
                              " ".join(w["text"] for w in pack_tokens)).strip()

                row = {
                    "product_name": name,
                    "opening_stock": opening,
                    "purchase_stock": purchase,
                    "sales_qty": sales,
                    "closing_stock": closing,
                }
                if pack:
                    row["pack"] = pack
                records.append(row)

    return records
