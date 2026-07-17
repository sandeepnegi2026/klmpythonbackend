"""PharmAssist (C-Square) 'Stock and Sale Report' — SINGLE-PAGE wide family.

Sibling of pharmassist_stock_sale (which splits the column band across two physical
pages). Here the whole band prints inline. One report per KLM division (COSMO /
COSMOQ / COSMOCOR / DERMA / DERMACOR / PED / PHARMA ...). The engine emits the SAME
report at several column widths across vendors; observed headers:

  DELTA PHARMA (wide):
    Item Pack Apr Mar Op. Pur SP Sale SS BrBsc qt Cr Db Adj Bal. BVal SVal Order
  RSK (wide, split Br/Bsc, prior months Feb/Jan):
    Item Pack Feb Jan Op. Pur SP Sale SS Br Bsc qt Cr Db Adj Bal. BVal SVal Order
  BANERJEE (narrow, no prior months / Adj / Order):
    Item Pack Op. Pur SP Sale SS BrBsc qt Cr Db Bal. BVal SVal

So the parser is HEADER-DRIVEN: it reads the printed header row, anchors every column
it recognises, and buckets each data number into a column by matching the number's
RIGHT edge (x1) to the label's right edge — the numbers are right-aligned with BLANK
interior cells, and the text layer glyph-interleaves the name/pack characters with the
leading digits, so a flat token parse cannot align columns. Rows are clustered by top
with a tolerance (the header/data baselines jitter ~1-3 px and straddle integer top
boundaries, which naive round(top) bucketing would split).

Prior-month columns (any of Jan..Dec) are previous-period sales — informational, dropped.
Reconcile (verified on DELTA + BANERJEE; RSK mostly):
    closing(Bal) = opening(Op) + purchase(Pur) + Σ inflow(SP,Br,Bsc,qt,Cr) - sale(Sale) - Σ outflow(SS,Db)
Secondary inflows fold into purchase_free, secondary outflows into sales_free, so
    closing = opening + purchase_stock + purchase_free - sales_qty - sales_free.
Adj is a signed stock adjustment (usually negative) that folds into the inflow sum
(verified on RSK: NIOFINE TAB 113+50-2+(-1)=160=Bal). Order is the trailing order-qty
shortfall column and is NOT part of movement. BVal = closing (balance) value, SVal =
sale value. A handful of rows carry a genuine vendor qty mismatch even though their
value totals tie out to the printed block, so a file may land GREEN or AMBER honestly.
"""
import io
import re

_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?$")

_MONTHS = {"Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"}

# printed header token -> internal column key. Month tokens map to "prior" (ignored).
# "BrBsc" is the glued form of the split "Br"/"Bsc" pair; both are secondary inflows.
_COL_MAP = {
    "Op.": "Op", "Pur": "Pur", "SP": "SP", "Sale": "Sale", "SS": "SS",
    "BrBsc": "Br", "Br": "Br", "Bsc": "Bsc", "qt": "qt", "Cr": "Cr", "Db": "Db",
    "Adj": "Adj", "Bal.": "Bal", "BVal": "BVal", "SVal": "SVal", "Order": "Order",
}

# columns required in every variant -> proof this row is really the header
_REQUIRED = ("Op", "Pur", "Sale", "Bal", "BVal")

_INFLOW = ("SP", "Br", "Bsc", "qt", "Cr", "Adj")   # secondary inflows -> purchase_free
_OUTFLOW = ("SS", "Db")                             # secondary outflows -> sales_free

_SKIP_PREFIXES = ("manufacturer", "for manufacturer", "opening val", "closing val",
                  "sales :", "sales:", "note :", "note:", "printed using",
                  "report date", "page ", "stock and sale report")


def _is_num(t):
    return bool(_NUM_RE.fullmatch(t.replace(",", ""))) and any(c.isdigit() for c in t)


def _to_f(t):
    try:
        return float(t.replace(",", ""))
    except ValueError:
        return 0.0


def _cluster_rows(words, tol=4):
    """Group words into visual rows: tops within `tol` px of the cluster start belong
    together (the header/data baselines jitter 1-3 px and can straddle an integer
    boundary, which a plain round(top) bucket would split)."""
    by_top = {}
    for w in words:
        by_top.setdefault(round(w["top"], 1), []).append(w)
    rows, cur, start = [], [], None
    for top in sorted(by_top):
        if start is None or top - start <= tol:
            if start is None:
                start = top
            cur.extend(by_top[top])
        else:
            rows.append(cur)
            cur, start = list(by_top[top]), top
    if cur:
        rows.append(cur)
    return rows


def _header_anchors(row):
    """If this word row is the column header, return anchors keyed by column with the
    label RIGHT edge (x1) for bucketing, plus name/pack split boundaries. Month tokens
    are anchored as 'prior' (ignored when read)."""
    right, x0 = {}, {}
    for w in row:
        t = w["text"]
        if t in _MONTHS:
            right.setdefault("prior@%.0f" % w["x1"], w["x1"])
            x0["_prior_min"] = min(x0.get("_prior_min", 1e9), w["x0"])
        elif t in _COL_MAP:
            right[_COL_MAP[t]] = w["x1"]
            x0[_COL_MAP[t]] = w["x0"]
        elif t == "Pack":
            x0["Pack"] = w["x0"]
    if not all(k in right for k in _REQUIRED):
        return None
    # first data column left edge: leftmost of the prior-month block or Op
    first = min(x0.get("_prior_min", 1e9), x0.get("Op", 1e9))
    return {
        "right": right,
        "_pack": x0.get("Pack", 110),
        "_first": first if first < 1e8 else x0.get("Op", 145),
        "_bal": x0.get("Bal", 454),
    }


def _bucket(nums, right_edges):
    """Assign each number to the column whose label right-edge (x1) is closest to the
    number's own right-edge — robust for right-aligned, blank-interior cells."""
    cols = list(right_edges.items())
    col = {}
    for w in nums:
        wx1 = w["x1"]
        placed = min(cols, key=lambda kv: abs(kv[1] - wx1))[0]
        col[placed] = _to_f(w["text"])
    return col


def parse_pharmassist_stock_sale_single(text, file_bytes=None):
    if not file_bytes:
        return []
    import pdfplumber

    records = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        anchors = None
        for page in pdf.pages:
            for row in _cluster_rows(page.extract_words()):
                row = sorted(row, key=lambda w: w["x0"])
                found = _header_anchors(row)
                if found:
                    anchors = found
                    continue
                if not anchors:
                    continue

                pack_x = anchors["_pack"]
                first_x = anchors["_first"]
                bal_x = anchors["_bal"]

                low_line = " ".join(w["text"] for w in row).strip().lower()
                if any(low_line.startswith(p) for p in _SKIP_PREFIXES):
                    continue

                def _is_data_num(w):
                    return _is_num(w["text"]) and w["x0"] >= first_x - 12

                nums = [w for w in row if _is_data_num(w)]
                name_toks = [w["text"] for w in row
                             if w["x0"] < pack_x and not _is_data_num(w)]
                pack_toks = [w["text"] for w in row
                             if pack_x <= w["x0"] < bal_x and not _is_data_num(w)]

                name = " ".join(name_toks).strip()
                if not name or not name[0].isalpha() or not nums:
                    continue

                col = _bucket(nums, anchors["right"])
                op = col.get("Op", 0.0)
                pur = col.get("Pur", 0.0)
                sale = col.get("Sale", 0.0)
                bal = col.get("Bal", 0.0)
                extras_in = sum(col.get(c, 0.0) for c in _INFLOW)
                extras_out = sum(col.get(c, 0.0) for c in _OUTFLOW)

                if (op == 0 and pur == 0 and sale == 0 and bal == 0
                        and extras_in == 0 and extras_out == 0):
                    continue

                records.append({
                    "product_name": name,
                    "pack": " ".join(pack_toks).strip(),
                    "opening_stock": op,
                    "purchase_stock": pur,
                    "purchase_free": extras_in,
                    "sales_qty": sale,
                    "sales_free": extras_out,
                    "closing_stock": bal,
                    "closing_stock_value": col.get("BVal", 0.0),
                    "sales_value": col.get("SVal", 0.0),
                    "order_qty": col.get("Order", 0.0),
                })
    return records
