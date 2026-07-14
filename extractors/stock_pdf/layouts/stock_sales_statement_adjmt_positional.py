"""SREE SUPREME PHARMA (NAMAKKAL) DOS-style "STOCK & SALES STATEMENT".

One PDF per KLM division (CASMO/COSMO COR/COSMO Q/DERMA COR/DERMA/PEDIA/PHARMA).
DOSPrinter dot-matrix export with a grouped, two-row column header:

    PRODUCT NAME PACKG OPENING RECEIPT <-----SALES-----> ADJMT CLOSING CLOSING AGE
                        QTY    QTY FREE  LAST  QTY FREE  STOCK   QTY FREE VALUE DAYS

Every zero cell prints an explicit '-', so the trailing-token COUNT varies per row
(a flat text parse cannot align columns once several dashes collapse). The numbers
are RIGHT-aligned to fixed x-positions, so this is parsed POSITIONALLY: each number
is bucketed into its column by matching its right edge (x1) to the sub-header label's
right edge. Column x-positions are rock-stable across all 7 division files.

Column -> canonical mapping (dashes are nil = 0):
  OPENING QTY            -> opening_stock
  RECEIPT QTY            -> purchase_stock        (inflow)
  RECEIPT FREE           -> purchase_free         (inflow)
  SALES LAST             -> (prev-month qty; IGNORED, maps nowhere)
  SALES QTY              -> sales_qty             (outflow)
  SALES FREE             -> sales_free            (outflow)
  ADJMT STOCK            -> stock_adjustment      (informational; always '-' in samples)
  CLOSING QTY            -> closing_stock         <-- the real closing (NOT closing free)
  CLOSING FREE           -> closing_free
  CLOSING VALUE          -> closing_stock_value   (rupees)
  AGE DAYS               -> (dropped)

Reconcile (verified on every moving row, e.g. HISTABIL 20+51+10-40-20=21;
EKRAN 80 SUNSCREEN 17+1+2-6-3=11): closing = opening + purchase_stock +
purchase_free - sales_qty - sales_free. The postprocess sanity check uses exactly
this equation, so it PASSES for the printed rows.

The KLM6 file appends a SECOND "EXPIRES ON / PRODUCT NAME PACKING BATCH NO. EXPIRY
QTY" batch-expiry table; its header has PACKING at a different x and no OPENING/
RECEIPT columns, so it never re-arms the stock anchors and its rows are ignored.
"""
import io

import pdfplumber

# printed sub-header label -> internal column key, paired with the label's ORDER so
# repeated labels (QTY appears 4x, FREE 3x) are disambiguated left-to-right.
# The bucket anchor is the label's right edge (x1); numbers are right-aligned to it.
_SUBHEADER_SEQUENCE = [
    "opening_stock",   # OPENING QTY
    "purchase_stock",  # RECEIPT QTY
    "purchase_free",   # RECEIPT FREE
    "_sales_last",     # SALES LAST (ignored)
    "sales_qty",       # SALES QTY
    "sales_free",      # SALES FREE
    "_adjmt",          # ADJMT STOCK
    "closing_stock",   # CLOSING QTY
    "closing_free",    # CLOSING FREE
    "closing_stock_value",  # CLOSING VALUE
    "_age",            # AGE DAYS
]
# Expected sub-header token stream (top row of the header pair). Used only to
# recognise the sub-header row; column keys come from _SUBHEADER_SEQUENCE by order.
_SUBHEADER_TOKENS = ["QTY", "QTY", "FREE", "LAST", "QTY", "FREE",
                     "STOCK", "QTY", "FREE", "VALUE", "DAYS"]

# x0 below this belongs to product NAME; the PACKG column starts ~x0=132 and the
# first data number (OPENING QTY) starts ~x0=170. Split name | pack | numbers.
_PACK_X0 = 130.0
_NUM_X0 = 165.0

_SKIP_PREFIXES = (
    "product name", "qty", "opening value", "sales value",
    "last month sales", "* --->", "-----", "expires on", "dosprinter",
    "stock & sales", "sree supreme", "company", "page no",
)


def _is_num_token(t):
    s = t.replace(",", "").rstrip(".")
    return bool(s) and any(c.isdigit() for c in s) and all(
        c.isdigit() or c == "." for c in s
    )


def _to_f(t):
    try:
        return float(t.replace(",", "").rstrip("."))
    except ValueError:
        return 0.0


def _extract_word_rows(file_bytes):
    """Yield (page_index, [word,...]) rows clustered by y-top, x-sorted."""
    out = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for pi, page in enumerate(pdf.pages):
            words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
            by_top = {}
            for w in words:
                key = round(w["top"])
                # merge near-equal tops (dot-matrix baselines wobble ~1px)
                matched = None
                for k in by_top:
                    if abs(k - key) <= 1:
                        matched = k
                        break
                by_top.setdefault(matched if matched is not None else key, []).append(w)
            for top in sorted(by_top):
                out.append((pi, sorted(by_top[top], key=lambda w: w["x0"])))
    return out


def _is_subheader(row):
    """True if this row is the QTY/QTY/FREE/... second header line."""
    toks = [w["text"] for w in row]
    return toks == _SUBHEADER_TOKENS


def _subheader_anchors(row):
    """Map each column key to its sub-header label right edge (x1), in order."""
    anchors = {}
    for key, w in zip(_SUBHEADER_SEQUENCE, row):
        anchors[key] = w["x1"]
    return anchors


def _bucket_numbers(nums, anchors):
    """Assign each numeric word to the nearest column by right-edge distance."""
    cols = list(anchors.items())
    out = {}
    for w in nums:
        key = min(cols, key=lambda kv: abs(kv[1] - w["x1"]))[0]
        out[key] = _to_f(w["text"])
    return out


def parse_stock_sales_statement_adjmt_positional(text, file_bytes=None):
    if not file_bytes:
        return []

    records = []
    anchors = None
    for _page, row in _extract_word_rows(file_bytes):
        if _is_subheader(row):
            anchors = _subheader_anchors(row)
            continue
        if anchors is None:
            continue

        line_low = " ".join(w["text"] for w in row).strip().lower()
        if not line_low or any(line_low.startswith(p) for p in _SKIP_PREFIXES):
            # A new "PRODUCT NAME ... PACKING BATCH" header (KLM6 expiry table) starts
            # with "product name" -> disarm so its batch rows are never parsed.
            if line_low.startswith("product name") or line_low.startswith("expires on"):
                anchors = None
            continue

        name_toks = [w["text"] for w in row if w["x0"] < _PACK_X0]
        pack_toks = [w["text"] for w in row if _PACK_X0 <= w["x0"] < _NUM_X0]
        nums = [w for w in row if w["x0"] >= _NUM_X0 and _is_num_token(w["text"])]

        name = " ".join(name_toks).strip()
        pack = " ".join(pack_toks).strip()
        if not name or not nums:
            continue

        col = _bucket_numbers(nums, anchors)
        # drop non-canonical / prev-month cells before emitting
        rec = {
            "product_name": name,
            "pack": pack,
            "opening_stock": col.get("opening_stock", 0.0),
            "purchase_stock": col.get("purchase_stock", 0.0),
            "purchase_free": col.get("purchase_free", 0.0),
            "sales_qty": col.get("sales_qty", 0.0),
            "sales_free": col.get("sales_free", 0.0),
            "closing_stock": col.get("closing_stock", 0.0),
            "closing_free": col.get("closing_free", 0.0),
            "closing_stock_value": col.get("closing_stock_value", 0.0),
        }
        adj = col.get("_adjmt")
        if adj:
            rec["stock_adjustment"] = adj

        # skip fully-empty rows (every movement/closing cell is a dash -> all 0)
        if not any(rec[k] for k in (
            "opening_stock", "purchase_stock", "purchase_free",
            "sales_qty", "sales_free", "closing_stock", "closing_stock_value",
        )):
            continue

        records.append(rec)

    return records
