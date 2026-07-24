"""PharmAssist (C-Square) 'Stock and Sales Mfac Group Wise Report'.

The text extraction glyph-interleaves the Item/Pack characters with the leading
numeric columns (e.g. "SERUM3 03 0MMLL" for "SERUM 30ML"), so a flat text parse
cannot align the columns. We read word x-positions with pdfplumber instead and
bucket each number into its column using the printed header row as the anchor.

Header:  Item | Pack | Apr | Mar | Op. | Pur | SP | Sale | SS | Br | Cr | Db | Adj | Bal. | BVal | SVal | Order

Bal(closing) = Op + Pur + SP + Br + Cr + Adj - Sale - SS - Db  (verified 319/320 rows).
Apr/Mar are previous-month sales (ignored). Every column besides Op/Pur/Sale is a
secondary inflow/outflow with no dedicated canonical field, so — the marg_open_pur_free_sale
precedent — secondary inflows fold into purchase_free and secondary outflows into
sales_free, leaving closing = opening + purchase_stock + purchase_free - sales_qty - sales_free.
"""
import io
import re

_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?$")
# canonical target for each header column; None = ignore (previous-month sales / order / values handled separately)
_INFLOW_EXTRA = ("SP", "Br", "Cr", "Adj")   # secondary inflows -> purchase_free
_OUTFLOW_EXTRA = ("SS", "Db")               # secondary outflows -> sales_free
_HEADER_TOKENS = ("Op.", "Pur", "Sale", "Bal.", "Order")


def _is_num(t):
    return bool(_NUM_RE.fullmatch(t.replace(",", "")))


def _to_f(t):
    return float(t.replace(",", ""))


def _header_anchors(words):
    """Return {col_name: x0} if this word list is the column header row, else None."""
    labels = {w["text"]: w["x0"] for w in words}
    if not all(tok in labels for tok in _HEADER_TOKENS):
        return None
    want = ["Apr", "Mar", "Op.", "Pur", "SP", "Sale", "SS", "Br", "Cr", "Db",
            "Adj", "Bal.", "BVal", "SVal", "Order"]
    anchors = {}
    for name in want:
        if name in labels:
            anchors[name.rstrip(".")] = labels[name]
    return anchors if "Op" in anchors and "Bal" in anchors else None


def parse_pharmassist_mfac(text, file_bytes=None):
    if not file_bytes:
        return []
    import pdfplumber

    records = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        anchors = None
        for page in pdf.pages:
            words = page.extract_words()
            by_top = {}
            for w in words:
                by_top.setdefault(round(w["top"]), []).append(w)

            # --- fragment recovery (additive; preserves all existing behaviour) ---
            # Some C-Square exports render a single visual row with sub-pixel top
            # jitter (e.g. cells at top=140.38 and top=140.85). round(top) then splits
            # that one row across two integer buckets and orphans the straddling cell
            # (typically BVal / Order / a stray qty), which is silently dropped. We
            # keep the ORIGINAL round(top) grouping, name derivation, name_cut and
            # anchor detection untouched; we only look into the neighbouring bucket
            # (top-1 / top+1) for numeric stragglers that sit within intra-row jitter
            # of this row's own numeric band and fill a column slot this row left
            # empty. Nothing here can add/remove a row or change a name.
            def _recover_strays(top, row_words):
                own_nums = [w for w in row_words if _is_num(w["text"])]
                if not own_nums:
                    return []
                own_tops = [w["top"] for w in own_nums]
                lo, hi = min(own_tops), max(own_tops)
                taken = {id(w) for w in row_words}
                strays = []
                for nb in (top - 1, top + 1):
                    for w in by_top.get(nb, []):
                        if id(w) in taken or not _is_num(w["text"]):
                            continue
                        # only a true intra-row straggler: its top must lie within a
                        # tight jitter band of this row's numeric cells (< 0.6px past
                        # the row's own numeric spread), i.e. the same visual line.
                        if (lo - 0.6) <= w["top"] <= (hi + 0.6):
                            strays.append(w)
                return strays

            for top in sorted(by_top):
                row_words = sorted(by_top[top], key=lambda w: w["x0"])
                found = _header_anchors(row_words)
                if found:
                    anchors = found
                    continue
                if not anchors:
                    continue

                # ordered (name, x0) column boundaries for this page
                order = [c for c in ["Apr", "Mar", "Op", "Pur", "SP", "Sale", "SS",
                                     "Br", "Cr", "Db", "Adj", "Bal", "BVal", "SVal", "Order"]
                         if c in anchors]
                xs = [anchors[c] for c in order]
                name_cut = anchors.get("Apr", 160) - 8

                nums = [w for w in row_words if _is_num(w["text"]) and w["x0"] >= name_cut - 4]
                if len(nums) < 4:
                    continue
                name = " ".join(w["text"] for w in row_words if w["x0"] < name_cut).strip()
                low = name.lower()
                if not name or "group" in low or "val." in low or "manufacturer" in low:
                    continue

                col = {}
                for w in nums:
                    cx = (w["x0"] + w["x1"]) / 2.0
                    for i, c in enumerate(order):
                        left = xs[i] - 6
                        right = (xs[i + 1] - 6) if i + 1 < len(xs) else 610
                        if left <= cx < right:
                            col[c] = _to_f(w["text"])
                            break

                # Fill only column slots left empty by orphaned stragglers from the
                # jitter-split neighbour bucket. Never overwrite a cell we already read.
                for w in _recover_strays(top, row_words):
                    if w["x0"] < name_cut - 4:
                        continue
                    cx = (w["x0"] + w["x1"]) / 2.0
                    for i, c in enumerate(order):
                        left = xs[i] - 6
                        right = (xs[i + 1] - 6) if i + 1 < len(xs) else 610
                        if left <= cx < right:
                            if c not in col:
                                col[c] = _to_f(w["text"])
                            break

                if "Bal" not in col:
                    continue
                purchase_free = sum(col.get(c, 0.0) for c in _INFLOW_EXTRA)
                sales_free = sum(col.get(c, 0.0) for c in _OUTFLOW_EXTRA)
                records.append({
                    "product_name": name,
                    "opening_stock": col.get("Op", 0.0),
                    "purchase_stock": col.get("Pur", 0.0),
                    "purchase_free": purchase_free,
                    "sales_qty": col.get("Sale", 0.0),
                    "sales_free": sales_free,
                    "closing_stock": col.get("Bal", 0.0),
                    "closing_stock_value": col.get("BVal", 0.0),
                    "sales_value": col.get("SVal", 0.0),
                    "order_qty": col.get("Order", 0.0),
                })
    return records
