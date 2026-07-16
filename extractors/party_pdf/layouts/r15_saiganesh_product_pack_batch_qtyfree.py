import io
import re

# ---------------------------------------------------------------------------
# SAI GANESH PHARMA (RAIPUR C.G., KLM distributor) — "SALES REPORT",
# product-detail (batch-wise) party sales.
# Source file: SAI GANESH PHARMA/Party report/klmpedia.pdf
#
# The PDF interleaves TWO independent reports across alternating pages:
#   * a party summary list  ("PARTY CITY DATE INVNO" -> <name> <city> <dd/mm/yyyy>
#     <invoice_amount>") — a bill-value roll-up with NO product/quantity data;
#   * a product-detail list ("PRODUCT PACK BATCH QTY FREE MRP RATE AMOUNT")
#     grouped per bill, each bill block closed by an all-zero-but-amount
#     subtotal line "0.00 0.00 0.00 0.00 <bill_total>".
# Only the product-detail rows carry the sellable QTY/FREE/RATE/AMOUNT, so those
# are the extracted records; the party summary pages and subtotal footers are
# dropped.
#
# GATE token (spaces stripped, lowercased) — the product column header:
#   "PRODUCT PACK BATCH QTY FREE MRP RATE AMOUNT"
#     -> "productpackbatchqtyfreemrprateamount"
#
# COLUMN SPLIT is POSITIONAL by word x0 — the eight columns are cleanly aligned
# in the source (header x0: PRODUCT 53, PACK 192, BATCH 242, QTY 320, FREE 345,
# MRP 384, RATE 414, AMOUNT 447). A text-based right-to-left peel is unsafe
# because product NAMES themselves end in size tokens ("APPYBUSH SYRUP 200ML",
# "SACCTIK GG ORAL DROP", "ARGICYNE SACHETS 6GM") that would be mis-swallowed
# into the PACK column. Using x-bands the PRODUCT column (x0 < 185) and the PACK
# column (185 <= x0 < 235) never overlap.
#
# Numeric columns are mapped by their fixed x-band, NEVER derived:
#   QTY   (310 <= x0 < 340), FREE (340 <= x0 < 365), MRP (365 <= x0 < 395),
#   RATE  (395 <= x0 < 435), AMOUNT (x0 >= 435).
# Reconcile (the source's own arithmetic): QTY * RATE == AMOUNT on every row,
# and the summed AMOUNT (283387.92) matches the printed grand-total line
# "0.00 0.00 0.00 0.00 283387.92". FREE is a genuine free-QTY column (-> free_qty);
# MRP and RATE are the two price columns; AMOUNT is the net value column.
# ---------------------------------------------------------------------------

H = [
    "Product Name",
    "Pack",
    "Batch",
    "Qty",
    "Free Qty",
    "MRP",
    "Rate",
    "Amount",
]

# Column x0 boundaries (left edge of each column), with tolerance.
# Boundaries derived from the value x0 positions (values are right-aligned, so
# each value's left edge sits a little LEFT of its header's left edge):
#   QTY ~316-322, FREE ~351-352, MRP ~375-381, RATE ~409-415, AMOUNT ~454-460.
_PACK_X0 = 185.0     # product < this <= pack
_BATCH_X0 = 235.0    # pack    < this <= batch
_QTY_X0 = 310.0      # batch   < this <= qty
_FREE_X0 = 340.0
_MRP_X0 = 365.0
_RATE_X0 = 395.0
_AMOUNT_X0 = 435.0

_MONEY = re.compile(r"^-?[\d,]+\.\d{1,2}$")


def _fnum(tok):
    try:
        return float(str(tok).replace(",", ""))
    except (ValueError, AttributeError):
        return 0.0


def _row_words(page):
    """Cluster a page's words into visual text rows by 'top' proximity."""
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
    """Bucket a row's words by x0 into the 8 columns. Returns
    (product, pack, batch, qty, free, mrp, rate, amount) as strings, or None if
    the row is not a valid product line (missing/invalid numeric tail)."""
    prod, pack, batch, qty, free, mrp, rate, amount = [], [], [], [], [], [], [], []
    for w in ws:
        x0 = w["x0"]
        t = w["text"]
        if x0 < _PACK_X0:
            prod.append(t)
        elif x0 < _BATCH_X0:
            pack.append(t)
        elif x0 < _QTY_X0:
            batch.append(t)
        elif x0 < _FREE_X0:
            qty.append(t)
        elif x0 < _MRP_X0:
            free.append(t)
        elif x0 < _RATE_X0:
            mrp.append(t)
        elif x0 < _AMOUNT_X0:
            rate.append(t)
        else:
            amount.append(t)

    qty_s = " ".join(qty).strip()
    free_s = " ".join(free).strip()
    mrp_s = " ".join(mrp).strip()
    rate_s = " ".join(rate).strip()
    amount_s = " ".join(amount).strip()
    prod_s = " ".join(prod).strip()

    # A real product row has decimal QTY, FREE, MRP, RATE and AMOUNT columns and
    # a non-empty product name. This rejects the party-summary rows (a date sits
    # in the QTY band) and the "0.00 0.00 0.00 0.00 <total>" subtotal footers
    # (they carry no product name).
    for s in (qty_s, free_s, mrp_s, rate_s, amount_s):
        if not _MONEY.match(s):
            return None
    if not prod_s:
        return None
    return (
        prod_s,
        " ".join(pack).strip(),
        " ".join(batch).strip(),
        qty_s,
        free_s,
        mrp_s,
        rate_s,
        amount_s,
    )


def parse_r15_saiganesh_product_pack_batch_qtyfree(text, file_bytes=None):
    if not file_bytes:
        return H, []
    import pdfplumber

    rows = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            for ws in _row_words(page):
                cols = _column_split(ws)
                if cols is None:
                    continue
                prod, pack, batch, qty, free, mrp, rate, amount = cols
                # Drop the all-zero subtotal footer defensively (product name is
                # already required, but guard against any stray).
                if _fnum(qty) == 0.0 and _fnum(amount) == 0.0 and _fnum(free) == 0.0:
                    continue
                rows.append([prod, pack, batch, qty, free, mrp, rate, amount])

    return H, rows
