"""MEYON DRUGS 'Stock Statement for the month of ...' — one report per division.

Vendor: MEYON DRUGS (CALICUT), KLM LABORATORIES divisions (7 pages, one
division per page: DERMACOR / COSMO / COSMOQ / DERMA / PHARMA / COSMOCOR /
PEDIA).

Wrapped 3-line column header (numeric cells are RIGHT-ALIGNED, blank when 0):

    ....................................  Prev. month Sales ..............
    Items Packing Rate Op_Stk Rcpts P.Ret Sales Hos.Sal Brk Repl Cl_Stk Value
    ....................................  APR   MAY  ....................

Because most of the eight movement columns are blank on any given row, the flat
extract_text() layer collapses the gaps and the generic fallback binds columns
positionally-by-count (mis-mapping Rate->opening, Value->closing qty, etc.).
This parser instead reads word x-coordinates via pdfplumber and buckets every
numeric word into the column whose header RIGHT-edge (x1) it aligns to (nearest
anchor; the columns are >40px apart so nearest-neighbour is unambiguous even
though the data cells sit a few px right of the header token).

Column map:
    APR / MAY          -> dropped (previous-month sales)
    Rate               -> rate
    Op_Stk             -> opening_stock
    Rcpts              -> purchase_stock
    P.Ret              -> purchase_return
    Sales              -> sales_qty
    Hos.Sal            -> sales_free   (hospital-sale outflow)
    Brk                -> sales_free   (breakage outflow, folded)
    Repl               -> sales_free   (replacement outflow, folded)
    Cl_Stk             -> closing_stock
    Value              -> closing_stock_value   ('NIL' -> 0)

Reconcile (row-wise, holds in the source):
    Cl_Stk = Op_Stk + Rcpts - P.Ret - Sales - Hos.Sal - Brk - Repl
  i.e. canonical closing = opening + purchase - purchase_return
                                    - sales_qty - sales_free
    Value  = Rate * Cl_Stk

Division comes from the page banner '<code> KLM LABORATORIES <DIV> Page N of M'.
Each page is a distinct division (NOT replicated), so all pages are parsed. Rows
stop at 'Company Total' (which only prints value figures, no qty totals).
"""
import io
import re

_NUM_RE = re.compile(r"^-?[\d,]+(?:\.\d+)?$")

# header tokens that must ALL be present for a word-row to be the column header
_HDR_REQUIRED = ("Items", "Op_Stk", "Rcpts", "Sales", "Cl_Stk", "Value")

# printed left-to-right order; every column bucketed by header RIGHT edge (x1).
# APR/MAY/Rate live on the wrapped prev-month/rate rows, resolved separately.
_MOVE_COLS = ("Op_Stk", "Rcpts", "P.Ret", "Sales", "Hos.Sal", "Brk", "Repl",
              "Cl_Stk", "Value")

_BANNER_RE = re.compile(r"KLM LABORATORIES\s+(.+?)\s+Page\s+\d+\s+of\s+\d+", re.I)


def _is_num(t):
    t = t.replace(",", "")
    return bool(_NUM_RE.fullmatch(t)) and any(c.isdigit() for c in t)


def _to_f(t):
    t = t.replace(",", "").strip()
    if t in ("", "-", "--", "NIL", "nil"):
        return 0.0
    try:
        return float(t)
    except ValueError:
        return 0.0


def _cluster_rows(words, tol=4.0):
    """Group words into physical rows by 'top', merging within `tol` px.

    A single printed line renders its name/pack, its prev-month cells and its
    movement cells at slightly different baselines (top 141.47 / 141.67 / 142.22
    for one row), so a bare round(top) shreds it. We sort by top and start a new
    row whenever the gap to the previous word's top exceeds `tol`.
    """
    ws = sorted(words, key=lambda w: (w["top"], w["x0"]))
    rows = []
    cur = []
    cur_top = None
    for w in ws:
        if cur_top is None or abs(w["top"] - cur_top) <= tol:
            cur.append(w)
            cur_top = w["top"] if cur_top is None else cur_top
        else:
            rows.append(sorted(cur, key=lambda x: x["x0"]))
            cur = [w]
            cur_top = w["top"]
    if cur:
        rows.append(sorted(cur, key=lambda x: x["x0"]))
    return rows


def _split_pack(name):
    """Peel a trailing pack token (e.g. '20GM', "10'S", '50ML', '15ML')."""
    m = re.search(
        r"\s+(\d+\s*(?:GM|ML|MG|G|L|'S|S|X\s*\d+|MG/\S+)\S*)$", name, re.I
    )
    if m:
        return name[: m.start()].strip(), m.group(1).strip()
    return name.strip(), ""


def parse_meyon_prevmonth_stock(text, file_bytes=None):
    if not file_bytes:
        return []
    import pdfplumber

    records = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            clustered = _cluster_rows(words)

            # ---- derive header anchors (right edges) for this page ----
            anchors = None
            rate_x1 = None
            for row in clustered:
                by_text = {}
                for w in row:
                    by_text.setdefault(w["text"], w)
                if all(t in by_text for t in _HDR_REQUIRED):
                    anchors = {c: by_text[c]["x1"] for c in _MOVE_COLS
                               if c in by_text}
                    if "Rate" in by_text:
                        rate_x1 = by_text["Rate"]["x1"]
                    break
            if not anchors or "Op_Stk" not in anchors:
                continue

            # nearest-anchor boundary: numbers left of (Op_Stk_x1 - 40) belong to
            # Rate/APR/MAY (dropped except Rate) — treat Rate as the col whose x1
            # is ~rate_x1; everything left of Rate is prev-month sales (drop).
            opstk_x1 = anchors["Op_Stk"]
            col_names = list(anchors.keys())
            col_x1 = [anchors[c] for c in col_names]

            for row in clustered:
                joined = " ".join(w["text"] for w in row)
                low = joined.lower()

                if "company total" in low:
                    continue
                if low.startswith(("items ", "prev.", "apr ")) or joined == "APR MAY":
                    continue
                if any(k in joined for k in
                       ("KLM LABORATORIES", "Stock Statement", "MEYON DRUGS")):
                    continue
                # dashed rule line
                stripped = joined.replace(" ", "")
                if stripped and set(stripped) <= set("-"):
                    continue

                # name = word tokens whose right edge is left of the Rate column
                # (name + packing live in x < ~230; Rate cells start ~320)
                name_parts = [w["text"] for w in row if w["x1"] < 230]
                if not name_parts:
                    continue
                name = " ".join(name_parts).strip()
                if not re.search(r"[A-Za-z]{3}", name):
                    continue

                # numeric words in the stats area
                nums = [w for w in row if _is_num(w["text"]) and w["x0"] >= 230]
                # 'NIL' in the Value column
                nil_words = [w for w in row
                             if w["text"].upper() == "NIL" and w["x0"] >= 700]

                col = {}
                for w in nums:
                    xr = w["x1"]
                    # Rate column: a decimal value whose right edge is near rate_x1
                    if rate_x1 is not None and abs(xr - (rate_x1 + 0.5)) <= 8:
                        col["Rate"] = _to_f(w["text"])
                        continue
                    # left of Op_Stk (minus buffer) => APR/MAY prev-month => drop
                    if xr < opstk_x1 - 25:
                        # could still be Rate if rate_x1 unknown; but Rate values
                        # are decimals — keep as rate if it has a dot
                        if "." in w["text"] and "Rate" not in col:
                            col["Rate"] = _to_f(w["text"])
                        continue
                    # nearest movement column by right edge
                    best_i, best_d = None, 22.0
                    for i, xc in enumerate(col_x1):
                        d = abs(xr - xc)
                        if d < best_d:
                            best_d, best_i = d, i
                    if best_i is not None:
                        col[col_names[best_i]] = _to_f(w["text"])
                for w in nil_words:
                    col["Value"] = 0.0

                op = col.get("Op_Stk", 0.0)
                rc = col.get("Rcpts", 0.0)
                pret = col.get("P.Ret", 0.0)
                sale = col.get("Sales", 0.0)
                hos = col.get("Hos.Sal", 0.0)
                brk = col.get("Brk", 0.0)
                repl = col.get("Repl", 0.0)
                cls = col.get("Cl_Stk", 0.0)
                val = col.get("Value", 0.0)
                rate = col.get("Rate", 0.0)

                if (op == 0 and rc == 0 and sale == 0 and cls == 0
                        and val == 0 and rate == 0):
                    continue  # phantom / no-data row

                pname, pack = _split_pack(name)
                records.append({
                    "product_name": pname,
                    "pack": pack,
                    "rate": rate,
                    "opening_stock": op,
                    "purchase_stock": rc,
                    "purchase_return": pret,
                    "sales_qty": sale,
                    "sales_free": hos + brk + repl,
                    "closing_stock": cls,
                    "closing_stock_value": val,
                })

    return records
