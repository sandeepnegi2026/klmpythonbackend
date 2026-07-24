"""SRI SARAVANA PHARMA (Dharmapuri) 'Stock And Sales Report(Month)' — KLM divisions.

One PDF per KLM division (COSMO AND ORTHO / COSMO CORE / PEDIA AND GYNEC ...). Same
'Stock And Sales Report(Month)' title as the other KLM per-division month siblings
(klm_stock_sales_month / _repq / _rcpt / _urate / _tots / _prv2 / _netstock), but a
DISTINCT column vocabulary whose single-row header reads:

    ProductName  Pack  OpnSt ClsStk StockValu  Sale Qua SalFre SalRep SalesNet  PurQt ILastNet

Note the unusual order: the CLOSING quantity + its money value are printed BEFORE the
sales columns, and PurQt (receipts) sits near the far right. Every zero cell prints
BLANK, so the flat text (page.extract_text) collapses whole rows to a bare
"NAME PACK" with no numbers — a text/token parser reads 0 movement and the file
looks empty (which is exactly why generic emitted near-nothing). The numbers are
RIGHT-aligned to rock-stable x-positions, so this is parsed POSITIONALLY: each
numeric word is bucketed into its column by matching its right edge (x1) to the
header label's right edge.

Header label right edges (x1), identical across all four sample books:
    OpnSt      154.4   -> opening_stock
    ClsStk     188.2   -> closing_stock            (the real closing QTY)
    StockValu  236.3   -> closing_stock_value      (rupees; NOT closing_stock)
    Sale/Qua   279.7   -> sales_qty                (net sales quantity)
    SalFre     313.4   -> sales_free               (blank in all samples; kept for safety)
    SalRep     347.2   -> DROPPED  (a 'Sales Reported' informational count that is
                                    already netted into Sale Qua; feeding it into the
                                    sanity identity as sales_return breaks the ~3 rows
                                    that carry it, so it is not emitted)
    SalesNet   395.3   -> sales_value              (net sales rupees)
    PurQt      424.2   -> purchase_stock           (receipts / inflow qty; may be -ve)
    ILastNet   467.6   -> DROPPED  (prior-month net value; outside this month's book)

Reconcile identity (the postprocess sanity check: closing == opening + purchase_stock
+ purchase_free - purchase_return - sales_qty - sales_free + sales_return). In these
books purchase_free/return and sales_free/return are blank, so it reduces to:

    ClsStk == OpnSt + PurQt - Sale Qua

verified to hold on 100% of the rows that print a closing qty across all four files
(e.g. ZYDIP LOTION 50ML 35+60-65=30; CUTIHEAL 20+30-20=30; SPASTRET 40+35-75=0).
The mis-map generic produced (dumping StockValu into closing_stock etc.) is exactly
the audit finding this layout fixes.

Money reconcile (per file, x-aligned GRAND TOTAL footer between the last two dashed
rules): sum(closing_stock_value) == printed StockValu total, and sum(purchase_stock)
== printed PurQt total, to the paisa:
    cosmo and ortho  : StockValu 11333.37   PurQt 30
    COSMOCORE        : StockValu  9323.48   PurQt -84  (SaleQua 74, SalesNet 10414.87)
    PESIA AND GYNEC  : StockValu 50125.78   PurQt 224  (SaleQua 175, SalesNet 20043.43)

Multi-page: the ENTIRE report re-prints on every physical page (header + rows +
footer repeat), so rows are de-duplicated by (product_name, pack) — page 2 is an exact
copy, not a continuation. The GRAND TOTAL footer (a row of only numbers, no name text
left of the pack column) and the dashed rules / address / 'Admin -' / 'Document Footer'
banners are skipped.
"""
import io

import pdfplumber

# Header label -> canonical field, anchored on the label's right edge (x1). Labels
# printed as two words ('Sale'/'Qua') share one anchor (the right word). SalRep and
# ILastNet are intentionally absent -> their values fall to the nearest emitted
# anchor's neighbour and are discarded by _emit (we only read keys we map).
_HEADER_FIELDS = {
    "OpnSt": "opening_stock",
    "ClsStk": "closing_stock",
    "StockValu": "closing_stock_value",
    "Qua": "sales_qty",        # 'Sale Qua' -> the 'Qua' right edge
    "SalFre": "sales_free",
    "SalRep": "_sales_reported",   # dropped (already netted into sales_qty)
    "SalesNet": "sales_value",
    "PurQt": "purchase_stock",
    "ILastNet": "_ilast",          # dropped (prior-month value)
}
# fields we actually emit onto the record (SalRep/ILastNet excluded)
_EMIT = ("opening_stock", "closing_stock", "closing_stock_value",
         "sales_qty", "sales_free", "sales_value", "purchase_stock")

# words whose x0 is left of this are the product-name; between here and _NUM_X0 is pack
_PACK_X0 = 100.0
_NUM_X0 = 129.0   # header OpnSt x0 is 130.5; numbers start at/after this

# banner/rule/footer prefixes. Kept deliberately unambiguous: a bare "of"/"stock"
# would swallow real SKUs (e.g. OFACITIX), and the address/title/footer lines carry
# no numbers right of _NUM_X0 so the "no nums" guard already drops them anyway.
_SKIP_TOKENS = ("productname", "----")


def _is_num(t):
    s = t.replace(",", "")
    if not s or not any(c.isdigit() for c in s):
        return False
    body = s[1:] if s[:1] == "-" else s
    return all(c.isdigit() or c == "." for c in body)


def _to_f(t):
    try:
        return float(t.replace(",", ""))
    except ValueError:
        return 0.0


def _word_rows(file_bytes):
    """Yield x-sorted word rows clustered by y-top (2px tolerance) across all pages."""
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
            by_top = {}
            for w in words:
                key = round(w["top"])
                matched = None
                for k in by_top:
                    if abs(k - key) <= 2:
                        matched = k
                        break
                by_top.setdefault(matched if matched is not None else key, []).append(w)
            for top in sorted(by_top):
                yield sorted(by_top[top], key=lambda w: w["x0"])


def _header_anchors(row):
    """If this row is the ProductName ... header, map field -> label right-edge x1."""
    texts = [w["text"] for w in row]
    if "ProductName" not in texts or "OpnSt" not in texts or "ClsStk" not in texts:
        return None
    anchors = {}
    for w in row:
        field = _HEADER_FIELDS.get(w["text"])
        if field is not None:
            anchors[field] = w["x1"]
    # require the identifying quantity + value columns to have been located
    if not all(k in anchors for k in ("opening_stock", "closing_stock",
                                      "closing_stock_value", "purchase_stock")):
        return None
    return anchors


def _bucket(nums, anchors):
    """Assign each numeric word to the nearest column by right-edge distance."""
    items = list(anchors.items())
    out = {}
    for w in nums:
        field = min(items, key=lambda kv: abs(kv[1] - w["x1"]))[0]
        # first-writer wins per column (defends against a stray glued token)
        out.setdefault(field, _to_f(w["text"]))
    return out


def parse_sri_saravana_ss_month_positional(text, file_bytes=None):
    if not file_bytes:
        return []

    records = []
    seen = set()
    anchors = None
    for row in _word_rows(file_bytes):
        hdr = _header_anchors(row)
        if hdr is not None:
            anchors = hdr
            continue
        if anchors is None:
            continue

        name_toks = [w["text"] for w in row if w["x0"] < _PACK_X0]
        pack_toks = [w["text"] for w in row
                     if _PACK_X0 <= w["x0"] < _NUM_X0 and not _is_num(w["text"])]
        nums = [w for w in row if w["x0"] >= _NUM_X0 and _is_num(w["text"])]

        name = " ".join(name_toks).strip()
        low = name.lower()
        # skip banners / dashed rules / footer identity lines
        if not name or any(low.startswith(t) for t in _SKIP_TOKENS):
            continue
        # GRAND TOTAL footer prints only numbers (no name text left of pack) -> name empty
        if not nums:
            continue

        col = _bucket(nums, anchors)
        rec = {"product_name": name, "pack": " ".join(pack_toks).strip()}
        for f in _EMIT:
            rec[f] = col.get(f, 0.0)

        # drop rows with no movement AND no closing value (blank continuation lines)
        if not any(rec[f] for f in _EMIT):
            continue

        dedup = (rec["product_name"], rec["pack"])
        if dedup in seen:            # page-2 exact reprint
            continue
        seen.add(dedup)
        records.append(rec)

    return records
