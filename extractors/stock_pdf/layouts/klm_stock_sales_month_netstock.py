"""KLM 'Stock And Sales Report(Month)' — NetStock dialect (BIOLEND PHARMA TRADERS).

One report per KLM division (KLM-COSMO, KLM-COSMOCOR, KLM-COSMOQ, KLM-DERMA,
KLM-DERMACOR, KLM-PEDIA, KLM-PHARMA). Single physical page each.

The column header is printed as THREE stitched text rows::

    Opening   Pure   ILast      Total  NetStock
    Product Name  Pack   Sale Qty  Free  Rpl   Sale Net
    Stock     Qty    SalesQty   Stock  Val    @Pur

giving nine numeric columns (left -> right):

    Opening Stock | Pure Qty | ILast SalesQty | Sale Qty | Free | Rpl |
    Total Stock   | NetStock Val | Sale Net @Pur

Canonical mapping (fix_hint)::

    Opening Stock   -> opening_stock
    Pure Qty        -> purchase_stock
    Sale Qty        -> sales_qty
    Free            -> sales_free      (free goods given out; 0 on every sample)
    Total Stock     -> closing_stock
    NetStock Val    -> closing_stock_value
    Sale Net @Pur   -> sales_value

    ILast SalesQty  -> raw_ilast_salesqty  (previous-period sales, informational)
    Rpl             -> raw_rpl             (replacement; EXCLUDED from movement)

Reconciliation proven by the printed Grand Total on every file::

    closing = opening + purchase - sales          (Free = 0, Rpl excluded)

e.g. KLM-COSMO 321 + 238 - 177 = 382 = Total Stock; KLM-PEDIA 464 + 460 - 501
= 423. Because sales_free and purchase_free are 0 here, the canonical sanity
equation closing = opening + purchase + purchase_free + sales_return
- sales - sales_free - purchase_return holds directly.

Zero-movement products print their numeric cells BLANK, so the token count per
row is variable and a flat left/right split misaligns. All numbers are
RIGHT-ALIGNED and every column's right edge (x1) lines up column-by-column, so
we read word x-positions with pdfplumber and bucket each numeric word into the
column whose right-edge anchor it aligns to (small tolerance). The product name
is the run of tokens left of the pack region; pack tokens sit in a narrow band
just left of the first numeric column.

Rows with no numeric cells at all (e.g. 'AZACEA 20 CREAM' with a lone stray '0')
are discontinued/placeholder items and are skipped. The 'Grand Total' line and
the 'Opening stock value: / Previous sales: / Current sales: / Purchase value:'
footer band are skipped by name. This export renders the whole report on one
page; if a future export paginates, we stop after the page carrying the
grand-total tail (mirrors klm_stock_sales_month).
"""
import io
import re

_NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*$")

# right-edge (x1) anchors for the nine numeric columns, taken from the (stable,
# byte-identical across all seven division files) printed Grand Total row.
_ANCHORS = [
    ("opening", 255.0),
    ("pure", 291.5),
    ("ilast", 328.0),
    ("sale", 365.3),
    ("free", 391.0),
    ("rpl", 424.5),      # 424.1 / 426.1 across rows
    ("total", 463.6),
    ("netval", 521.5),
    ("salenet", 573.8),
]
_ANCHOR_TOL = 9.0        # column pitch is >= 25pt; blanks never straddle

# the first numeric column ('Opening') starts near x0 ~ 243; pack tokens sit in
# a narrow band just left of it.
_NUM_X0_MIN = 238.0
_PACK_X0_MIN = 195.0

# header labels that must ALL appear (compact, on the stitched rows) to confirm
# we are on the right report; used only as a defensive re-check, detection is
# already done upstream.
_HDR_TOKENS = ("Opening", "Pure", "ILast", "Total", "NetStock",
               "Free", "Rpl")


def _is_num(t):
    t = t.replace(",", "")
    return bool(_NUM_RE.fullmatch(t)) and any(c.isdigit() for c in t)


def _to_f(t):
    try:
        return float(t.replace(",", ""))
    except ValueError:
        return 0.0


def _bucket(word):
    """Return the column key whose right-edge anchor this word aligns to."""
    xr = word["x1"]
    best_key, best_d = None, _ANCHOR_TOL
    for key, xc in _ANCHORS:
        d = abs(xr - xc)
        if d < best_d:
            best_d, best_key = d, key
    return best_key


def parse_klm_stock_sales_month_netstock(text, file_bytes=None):
    if not file_bytes:
        return []
    import pdfplumber

    records = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            by_top = {}
            for w in words:
                by_top.setdefault(round(w["top"]), []).append(w)

            # confirm this page carries the stitched header (defensive)
            page_text = {w["text"] for w in words}
            if not all(t in page_text for t in _HDR_TOKENS):
                continue

            saw_grand_total = False

            for top in sorted(by_top):
                row = sorted(by_top[top], key=lambda w: w["x0"])
                joined = "".join(w["text"] for w in row)
                low = joined.lower()

                # dashed rule line
                if joined and set(joined) <= set("-"):
                    continue
                # header rows / footer band / grand total
                if low.startswith("grandtotal"):
                    # grand-total tail confirms the report is complete
                    saw_grand_total = True
                    continue
                if (low.startswith(("openingpure", "productname", "stockqty",
                                    "openingstockvalue", "purchasevalue",
                                    "division:", "biolend", "stockandsales"))
                        or "stockvalue:" in low or "currentstockvalue" in low):
                    continue

                nums = [w for w in row if _is_num(w["text"])
                        and w["x0"] >= _NUM_X0_MIN]
                if not nums:
                    continue

                name_toks = [w for w in row if w["x1"] < _PACK_X0_MIN]
                pack_toks = [w for w in row
                             if _PACK_X0_MIN <= w["x0"] < _NUM_X0_MIN]
                name = " ".join(w["text"] for w in name_toks).strip()
                pack = " ".join(w["text"] for w in pack_toks).strip()
                if not name:
                    continue

                col = {}
                for w in nums:
                    key = _bucket(w)
                    if key is not None:
                        col[key] = _to_f(w["text"])

                op = col.get("opening", 0.0)
                pur = col.get("pure", 0.0)
                sale = col.get("sale", 0.0)
                free = col.get("free", 0.0)
                total = col.get("total", 0.0)

                # placeholder / discontinued item — no real movement or stock
                if op == 0 and pur == 0 and sale == 0 and total == 0 \
                        and free == 0:
                    continue

                records.append({
                    "product_name": name,
                    "pack": pack,
                    "opening_stock": op,
                    "purchase_stock": pur,
                    "sales_qty": sale,
                    "sales_free": free,          # 0 on all samples
                    "closing_stock": total,
                    "closing_stock_value": col.get("netval", 0.0),
                    "sales_value": col.get("salenet", 0.0),
                    "raw_ilast_salesqty": col.get("ilast", 0.0),
                    "raw_rpl": col.get("rpl", 0.0),
                })

            # single-page export; stop once the grand-total tail is consumed so
            # a future paginated variant is not emitted N times.
            if saw_grand_total and records:
                break

    return records
