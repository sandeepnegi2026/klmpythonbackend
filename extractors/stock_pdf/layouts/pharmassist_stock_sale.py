"""PharmAssist (C-Square) 'Stock and Sale Report' — horizontal page-split variant.

Sibling of pharmassist_mfac. Same C-Square engine, but this export splits the
column band across TWO physical PDF pages per logical page ("Page N of M"):

  * LEFT page (even index):  Item Code | Item Name | Packing | Apr | Mar | Op. |
                             Pur | SP | Sale | SVal | SS   (Br header printed but
                             its data lives on the right page)
  * RIGHT page (odd index):  Br | Cr | Db | Adj | Bal. | BVal | Order

The two pages of a pair print their data rows at the SAME `top` y-coordinates, so
a row on the left page is stitched to the row at the matching top on the following
right page. The Item Code (leading ``I#####`` token) is present only on the left
page and keys the record.

The text layer glyph-interleaves the Item/Pack characters with the leading numeric
columns (e.g. "L1O5T0MIOLN 150M41L"), so a flat text parse cannot align columns.
We read word x-positions with pdfplumber and bucket each number into its column
using the printed header row as the x-anchor.

Reconcile:  Bal = Op + Pur + SP + Br + Cr + Adj - Sale - SS - Db.
Apr/Mar are previous-month sales (ignored). As in pharmassist_mfac / the
marg_open_pur_free_sale precedent, secondary inflows (SP, Br, Cr, Adj) fold into
purchase_free and secondary outflows (SS, Db) into sales_free, leaving
closing = opening + purchase_stock + purchase_free - sales_qty - sales_free.
"""
import io
import re

from extractors.stock_pdf.parse_common import _zero_row_is_product

_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?$")
_ITEM_RE = re.compile(r"^I\d{3,}$")

_INFLOW_EXTRA = ("SP", "Br", "Cr", "Adj")   # secondary inflows -> purchase_free
_OUTFLOW_EXTRA = ("SS", "Db")               # secondary outflows -> sales_free

# unique header tokens per side
_LEFT_TOKENS = ("Op.", "Pur", "Sale", "SVal")
_RIGHT_TOKENS = ("Br", "Cr", "Bal.", "BVal", "Order")

# ordered left-block value columns (name/pack live left of Apr)
_LEFT_ORDER = ["Apr", "Mar", "Op", "Pur", "SP", "Sale", "SVal", "SS"]
_RIGHT_ORDER = ["Br", "Cr", "Db", "Adj", "Bal", "BVal", "Order"]


def _is_num(t):
    return bool(_NUM_RE.fullmatch(t.replace(",", ""))) and any(c.isdigit() for c in t)


def _to_f(t):
    try:
        return float(t.replace(",", ""))
    except ValueError:
        return 0.0


def _left_anchors(labels):
    if not all(tok in labels for tok in _LEFT_TOKENS):
        return None
    want = ["Apr", "Mar", "Op.", "Pur", "SP", "Sale", "SVal", "SS"]
    anchors = {}
    for name in want:
        if name in labels:
            anchors[name.rstrip(".")] = labels[name]
    return anchors if "Op" in anchors and "Sale" in anchors else None


def _right_anchors(labels):
    if not all(tok in labels for tok in _RIGHT_TOKENS):
        return None
    want = ["Br", "Cr", "Db", "Adj", "Bal.", "BVal", "Order"]
    anchors = {}
    for name in want:
        if name in labels:
            anchors[name.rstrip(".")] = labels[name]
    return anchors if "Bal" in anchors and "Order" in anchors else None


def _bucket(nums, order, anchors, right_edge):
    """Assign each numeric word to its column by x-centre using midpoints of the
    ordered anchor x positions."""
    xs = [anchors[c] for c in order]
    col = {}
    for w in nums:
        cx = (w["x0"] + w["x1"]) / 2.0
        placed = None
        for i, c in enumerate(order):
            left = (xs[i - 1] + xs[i]) / 2.0 if i > 0 else xs[i] - 30
            right = (xs[i] + xs[i + 1]) / 2.0 if i + 1 < len(xs) else right_edge
            if left <= cx < right:
                placed = c
                break
        if placed is None:
            # past the last anchor -> last column
            if cx >= xs[-1]:
                placed = order[-1]
        if placed is not None:
            col[placed] = _to_f(w["text"])
    return col


def _parse_left_page(words):
    """Return {top: {'code','name','pack', left cols...}} for one left page."""
    by_top = {}
    for w in words:
        by_top.setdefault(round(w["top"]), []).append(w)

    anchors = None
    out = {}
    for top in sorted(by_top):
        row = sorted(by_top[top], key=lambda w: w["x0"])
        labels = {w["text"]: w["x0"] for w in row}
        found = _left_anchors(labels)
        if found:
            anchors = found
            continue
        if not anchors:
            continue

        # must start with an item code
        code_w = row[0]
        if not _ITEM_RE.match(code_w["text"]):
            continue

        apr_x = anchors["Apr"]
        name_cut = apr_x - 10
        nums = [w for w in row if _is_num(w["text"]) and w["x0"] >= name_cut - 4]
        name_pack = [w for w in row[1:] if w["x0"] < name_cut]
        # split name vs pack: packing column anchored ~244; name left of it
        name_toks = [w["text"] for w in name_pack if w["x0"] < 230]
        pack_toks = [w["text"] for w in name_pack if w["x0"] >= 230]

        col = _bucket(nums, _LEFT_ORDER, anchors, right_edge=apr_x + 320)
        rec = {
            "code": code_w["text"],
            "name": " ".join(name_toks).strip(),
            "pack": " ".join(pack_toks).strip(),
            "Op": col.get("Op", 0.0),
            "Pur": col.get("Pur", 0.0),
            "SP": col.get("SP", 0.0),
            "Sale": col.get("Sale", 0.0),
            "SVal": col.get("SVal", 0.0),
            "SS": col.get("SS", 0.0),
        }
        out[top] = rec
    return out


def _parse_right_page(words):
    """Return {top: {right cols...}} for one right page."""
    by_top = {}
    for w in words:
        by_top.setdefault(round(w["top"]), []).append(w)

    anchors = None
    out = {}
    for top in sorted(by_top):
        row = sorted(by_top[top], key=lambda w: w["x0"])
        labels = {w["text"]: w["x0"] for w in row}
        found = _right_anchors(labels)
        if found:
            anchors = found
            continue
        if not anchors:
            continue
        nums = [w for w in row if _is_num(w["text"])]
        if len(nums) < 3:
            continue
        col = _bucket(nums, _RIGHT_ORDER, anchors, right_edge=anchors["Order"] + 80)
        out[top] = {
            "Br": col.get("Br", 0.0),
            "Cr": col.get("Cr", 0.0),
            "Db": col.get("Db", 0.0),
            "Adj": col.get("Adj", 0.0),
            "Bal": col.get("Bal", 0.0),
            "BVal": col.get("BVal", 0.0),
            "Order": col.get("Order", 0.0),
        }
    return out


def parse_pharmassist_stock_sale(text, file_bytes=None):
    if not file_bytes:
        return []
    import pdfplumber

    records = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        pages = pdf.pages
        i = 0
        while i < len(pages):
            words = pages[i].extract_words()
            labels = {w["text"]: w["x0"] for w in words}
            if not _left_anchors(labels):
                i += 1
                continue

            left = _parse_left_page(words)
            right = {}
            if i + 1 < len(pages):
                rwords = pages[i + 1].extract_words()
                rlabels = {w["text"]: w["x0"] for w in rwords}
                if _right_anchors(rlabels):
                    right = _parse_right_page(rwords)

            for top in sorted(left):
                lrec = left[top]
                # match right row at the same top (allow +/-2 px jitter)
                rrec = right.get(top)
                if rrec is None:
                    for dt in (1, -1, 2, -2):
                        if (top + dt) in right:
                            rrec = right[top + dt]
                            break
                rrec = rrec or {}

                op = lrec["Op"]
                pur = lrec["Pur"]
                sale = lrec["Sale"]
                extras_in = lrec["SP"] + rrec.get("Br", 0.0) + rrec.get("Cr", 0.0) + rrec.get("Adj", 0.0)
                extras_out = lrec["SS"] + rrec.get("Db", 0.0)
                bal = rrec.get("Bal", 0.0)

                # Keep genuine zero-activity catalog SKUs (a listed product with no
                # movement, may still carry a closing/sales value); drop only a
                # nameless / address phantom the positional pass mis-captured.
                if (op == 0 and pur == 0 and sale == 0 and bal == 0
                        and extras_in == 0 and extras_out == 0
                        and not _zero_row_is_product(lrec["name"])):
                    continue

                records.append({
                    "product_code": lrec["code"],
                    "product_name": lrec["name"],
                    "pack": lrec["pack"],
                    "opening_stock": op,
                    "purchase_stock": pur,
                    "purchase_free": extras_in,
                    "sales_qty": sale,
                    "sales_free": extras_out,
                    "closing_stock": bal,
                    "closing_stock_value": rrec.get("BVal", 0.0),
                    "sales_value": lrec["SVal"],
                    "order_qty": rrec.get("Order", 0.0),
                })

            # advance past the pair (or single page if no right)
            i += 2 if right else 1
    return records
