"""VISNAGAR MEDICAL STORE (Marg) 'Stock and Sale Statement' — 10-column P.Val/S.Val variant.

Single-row column header:

    Item OpStk P.Qty P.Val P.Sch S.Qty S.Sch S.Val ClStk ClVal Order

This is the interleaved-item-code Marg export (product name letters/digits woven
together, e.g. 'VDSE0S6O7S0OFT CREAM 10GM' = code VS0670 + 'DESOSOFT CREAM 10GM';
downstream master-match recovers the clean catalog name). Unlike the plain
marg_opstk_statement layout, this variant interleaves the VALUE columns (P.Val,
S.Val) AND the SCHEME/free columns (P.Sch, S.Sch) between the quantity columns.

Every ZERO cell is BLANK (not printed), so a naive whitespace/positional-by-count
split mis-binds the movement columns the moment an interior cell collapses (e.g. a
row with a blank P.Sch shifts every later number one slot left). The numbers are
RIGHT-aligned to fixed x-positions, so this is parsed POSITIONALLY: each numeric
word is bucketed into its column by matching its right edge (x1) to the header
label's right edge, taken live from the printed 'OpStk P.Qty ... ClVal Order' row.

Column -> canonical mapping (blank cell = nil = 0):
  OpStk -> opening_stock
  P.Qty -> purchase_stock       (purchase received qty, IN)
  P.Val -> purchase_value       (value; NOT used for any quantity)
  P.Sch -> purchase_free        (purchase scheme / free goods received, IN)
  S.Qty -> sales_qty            (sold qty, OUT)
  S.Sch -> sales_free           (sales scheme / free goods issued, OUT)
  S.Val -> sales_value          (value; NOT used for any quantity)
  ClStk -> closing_stock        (the real closing qty)
  ClVal -> closing_stock_value  (value)
  Order -> (dropped; reorder suggestion, not a stock movement)

Reconcile (opening + purchase + purchase_free - purchase_return - sales_qty
- sales_free + sales_return = closing) holds on EVERY printed data row and on the
grand-total footer, verified programmatically (41/41 rows, footer 3549+1427+383
-1616-330 = 3413). There are no purchase_return / sales_return columns in this
export, so those slots stay 0. Quantities are never derived from a value column.

Gate token (compact, lowercased, spaces stripped column-header run, unique to this
export — the P.Val/P.Sch/S.Qty/S.Sch/S.Val interleave is not shared by any other
stock_pdf gate):
    'opstkp.qtyp.valp.schs.qtys.schs.valclstkclval'
"""
import io
import re

import pdfplumber

from extractors.stock_pdf.parse_common import _split_product_pack


# printed header label -> canonical key, in left-to-right order.
_HEADER_LABELS = [
    ("OpStk", "opening_stock"),
    ("P.Qty", "purchase_stock"),
    ("P.Val", "purchase_value"),
    ("P.Sch", "purchase_free"),
    ("S.Qty", "sales_qty"),
    ("S.Sch", "sales_free"),
    ("S.Val", "sales_value"),
    ("ClStk", "closing_stock"),
    ("ClVal", "closing_stock_value"),
    ("Order", "order"),
]
_REQUIRED_LABELS = [lbl for lbl, _ in _HEADER_LABELS]


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


def _clean_name(raw):
    """Strip the interleaved Marg item code prefix and any MF/VS code tokens.

    Leaves the name still lightly interleaved with the code digits/letters; the
    downstream catalog master-match resolves it to the canonical product name
    (this is the same treatment the plain marg_opstk_statement layout relies on).
    """
    n = re.sub(r"V[SI]\d{4}", " ", raw)
    n = re.sub(r"MF\d{3}", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    n, pack = _split_product_pack(n)
    n = re.sub(r"^[A-Z]{1,2}\d{3,5}\s*", "", n).strip()
    return n, pack


def _extract_word_rows(file_bytes):
    """Yield [word,...] rows clustered by y-top, x-sorted, across all pages."""
    out = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
            by_top = {}
            for w in words:
                key = round(w["top"])
                matched = None
                for k in by_top:
                    if abs(k - key) <= 1:
                        matched = k
                        break
                by_top.setdefault(matched if matched is not None else key, []).append(w)
            for top in sorted(by_top):
                out.append(sorted(by_top[top], key=lambda w: w["x0"]))
    return out


def _header_anchors(row):
    """Return {canonical_key: right-edge x1} if this row is the column header."""
    by_text = {w["text"]: w for w in row}
    if not all(lbl in by_text for lbl in _REQUIRED_LABELS):
        return None
    return {key: by_text[lbl]["x1"] for lbl, key in _HEADER_LABELS}


def parse_marg_item_opstk_pval_psch_sval(text, file_bytes=None):
    if not file_bytes:
        return []

    records = []
    anchors = None
    # smallest movement-column x0 boundary: names/pack sit left of the first number.
    name_x_max = 150.0

    for row in _extract_word_rows(file_bytes):
        # (re)arm anchors on each page's header row
        a = _header_anchors(row)
        if a is not None:
            anchors = a
            # numbers begin just left of the OpStk right edge; names end before that.
            name_x_max = anchors["opening_stock"] - 40.0
            continue
        if anchors is None:
            continue

        name_toks = [w["text"] for w in row if w["x0"] < name_x_max]
        nums = [
            w for w in row
            if w["x0"] >= name_x_max and _is_num_token(w["text"])
        ]
        if len(nums) < 2:
            continue

        raw_name = " ".join(name_toks).strip()
        # grand-total footer row has no name -> skip (its numbers do reconcile,
        # but it is not a product row).
        if not raw_name:
            continue

        name, pack = _clean_name(raw_name)
        if not name or len(name) < 3 or "*" in name:
            continue
        up = name.upper()
        if "DIVISION" in up or "DIVISON" in up or "DIVI" in up:
            continue

        col = {}
        for w in nums:
            key = min(anchors.items(), key=lambda kv: abs(kv[1] - w["x1"]))[0]
            col[key] = _to_f(w["text"])

        rec = {
            "product_name": name,
            "pack": pack,
            "opening_stock": col.get("opening_stock", 0.0),
            "purchase_stock": col.get("purchase_stock", 0.0),
            "purchase_value": col.get("purchase_value", 0.0),
            "purchase_free": col.get("purchase_free", 0.0),
            "purchase_return": 0.0,
            "sales_qty": col.get("sales_qty", 0.0),
            "sales_free": col.get("sales_free", 0.0),
            "sales_return": 0.0,
            "sales_value": col.get("sales_value", 0.0),
            "closing_stock": col.get("closing_stock", 0.0),
            "closing_stock_value": col.get("closing_stock_value", 0.0),
        }

        if not any(rec[k] for k in (
            "opening_stock", "purchase_stock", "purchase_free",
            "sales_qty", "sales_free", "closing_stock",
        )):
            continue

        records.append(rec)

    return records
