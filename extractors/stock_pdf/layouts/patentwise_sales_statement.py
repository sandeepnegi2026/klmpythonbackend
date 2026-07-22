"""CHANDRATHIL DRUG HOUSE / JACKSON DRUG HOUSE — DOSPrinter "Patentwise Sales
Statement" (one PDF per KLM division, banded by "KLM <DIV>" group headers).

Two-row grouped column header, 16 columns:

    Product Pack Op.Qty Purch. S.Ret. StkIn Sale Qty Free Qty Damage P.Ret. StkOut Balance Last  Purchase Sale  StockVa
                 Qty    Qty    Qty          Qty      Qty      Qty    Qty    Qty    Qty     Month  Value    Value lue
                                                     (JACKSON: 'Hosp' in place of 'Damage')

Every zero cell is blank (not '-'), so the trailing-token COUNT varies per row and a
flat text parse cannot align columns once several blanks collapse. The numbers are
RIGHT-aligned to a fixed x-grid (identical across CHANDRATHIL & JACKSON — same
DOSPrinter template/margins), so this is parsed POSITIONALLY: each number is bucketed
into its column by matching its right edge (x1) to the column anchor. A per-file
horizontal shift is derived from the "Op.Qty" header token so a re-margined sibling
still aligns.

Column -> canonical mapping (blank = 0; StkIn/StkOut/Last-Month are computed/derived
report columns that map nowhere):
  Op.Qty       -> opening_stock
  Purch.Qty    -> purchase_stock        (inflow)
  S.Ret.Qty    -> sales_return          (inflow — returned goods back to stock)
  StkIn Qty    -> (total inflow; dropped)
  Sale Qty     -> sales_qty             (outflow)
  Free Qty     -> sales_free            (outflow — free issued on sale)
  Damage/Hosp  -> exp_damage            (outflow)
  P.Ret.Qty    -> purchase_return       (outflow)
  StkOut Qty   -> (total outflow; dropped)
  Balance Qty  -> closing_stock
  Last Month SalesQty -> (dropped)
  Purchase Value -> purchase_value
  Sale Value     -> sales_value
  StockValue     -> closing_stock_value (rupees)

Reconcile — stock identity holds on every moving row (EKRAN AQUA 18+9-4=23;
HERPIVAL 1000 49+55-40-16=48; IMXIA F 28+11-19-8=12):
  closing = opening + purchase + s_return - sales - free - damage - p_return.
Value totals reconcile to the printed "GRAND TOTAL : <purchVal> <saleVal> <stockVal>"
(CHANDRATHIL 101299.91 / 115731.97 / 492879.05).

Excludes the "Patentwise AREAWISE Sales Statement" sibling (klm areawise.pdf): its
compact title is 'patentwiseareawisesalesstatement' (not '...salesstatement') and its
header is Product/Qty/Free/Total/Amount — no Op.Qty/StkOut/Balance — so both the detect
gate and this parser's header test skip it.
"""
import io
import re

import pdfplumber

# Column anchor = printed right edge (x1) of each numeric column, measured on
# CHANDRATHIL (JACKSON is byte-for-byte the same grid). Order is left-to-right;
# keys prefixed '_' are dropped before emit.
_BASE_ANCHORS = [
    ("opening_stock",       227.0),
    ("purchase_stock",      260.0),
    ("sales_return",        293.0),
    ("purchase_free",       320.0),   # "StkIn" — non-purchase inflow (transfer/adj in)
    ("sales_qty",           358.0),
    ("sales_free",          397.0),
    ("exp_damage",          432.0),
    ("purchase_return",     460.0),
    ("_stkout",             495.0),
    ("closing_stock",       530.0),
    ("_lastmonth",          581.0),
    ("purchase_value",      625.0),
    ("sales_value",         673.0),
    ("closing_stock_value", 718.0),
]
_OPENING_BASE_X1 = 227.0   # "Op.Qty" header right edge in the base geometry

_EMIT_KEYS = (
    "opening_stock", "purchase_stock", "purchase_free", "sales_return",
    "sales_qty", "sales_free", "exp_damage", "purchase_return", "closing_stock",
    "purchase_value", "sales_value", "closing_stock_value",
)

# page-top / footer / sub-header lines that repeat once armed (multi-page)
_SKIP_PREFIXES = (
    "product", "qty", "prev", "page", "from", "@@", "-----", "* ",
    "door", "patentwise",
)
_PACK_RE = re.compile(r"^\d+\.\d{2}$")


def _is_num(t):
    s = t.replace(",", "").rstrip(".")
    return bool(s) and any(c.isdigit() for c in s) and all(c.isdigit() or c == "." for c in s)


def _to_f(t):
    try:
        return float(t.replace(",", "").rstrip("."))
    except ValueError:
        return 0.0


def _rows_by_line(file_bytes):
    """Yield word-rows (x-sorted) clustered by y-top, in page order."""
    out = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
            lines = []
            for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
                for ln in lines:
                    if abs(ln[0]["top"] - w["top"]) <= 3:
                        ln.append(w)
                        break
                else:
                    lines.append([w])
            for ln in lines:
                out.append(sorted(ln, key=lambda w: w["x0"]))
    return out


def _header_geometry(row):
    """If row is the main column header, return (anchors, pack_x0, num_x0), else None."""
    by_text = {}
    for w in row:
        by_text.setdefault(w["text"], w)
    if not ({"Op.Qty", "Balance", "StkOut"} <= set(by_text)):
        return None
    shift = by_text["Op.Qty"]["x1"] - _OPENING_BASE_X1
    anchors = [(k, x + shift) for k, x in _BASE_ANCHORS]
    pack_w = by_text.get("Pack")
    op_w = by_text["Op.Qty"]
    if pack_w is not None:
        pack_x0 = pack_w["x0"] - 2.0
        num_x0 = (pack_w["x1"] + op_w["x0"]) / 2.0
    else:  # geometry fallback (base): pack 165-181, Op.Qty x0 204
        pack_x0, num_x0 = 160.0, 192.0
    return anchors, pack_x0, num_x0


def _bucket(nums, anchors):
    out = {}
    for w in nums:
        key = min(anchors, key=lambda kv: abs(kv[1] - w["x1"]))[0]
        out[key] = _to_f(w["text"])
    return out


def _clean_division(text):
    toks = [t for t in text.split() if t.upper() not in ("KLM", "LAB", "DIV.", "DIV")]
    return " ".join(toks).strip() or text.strip()


def parse_patentwise_sales_statement(text, file_bytes=None):
    if not file_bytes:
        return []
    anchors = None
    pack_x0 = num_x0 = 0.0
    division = ""
    records = []
    for row in _rows_by_line(file_bytes):
        geo = _header_geometry(row)
        if geo is not None:
            anchors, pack_x0, num_x0 = geo
            continue
        if anchors is None:
            continue
        line_low = " ".join(w["text"] for w in row).strip().lower()
        if not line_low:
            continue

        nums = [w for w in row if w["x0"] >= num_x0 and _is_num(w["text"])]
        if not nums:
            # division band header ("KLM COSMO", "KLM LAB COSMOCOR DIV.") — the only
            # no-number rows that carry data context; everything else (vendor, address,
            # title, sub-header) is ignored. A zero-movement PRODUCT whose name also
            # starts with "KLM" (e.g. "KLM D3 60K CAP8'S 8.00") carries a pack token in
            # the pack zone, so require the division band to have NO pack token.
            has_pack = any(pack_x0 <= w["x0"] < num_x0 and _PACK_RE.match(w["text"]) for w in row)
            if line_low.startswith("klm") and not has_pack:
                division = _clean_division(" ".join(w["text"] for w in row))
            continue
        if line_low.startswith(_SKIP_PREFIXES):
            continue

        name = " ".join(w["text"] for w in row if w["x0"] < pack_x0).strip()
        pack_toks = [w["text"] for w in row if pack_x0 <= w["x0"] < num_x0]
        pack = next((t for t in pack_toks if _PACK_RE.match(t)), "")
        if not name:
            continue

        col = _bucket(nums, anchors)
        rec = {"product_name": name, "pack": pack, "division": division}
        for k in _EMIT_KEYS:
            rec[k] = col.get(k, 0.0)
        # "StkOut" (transfer/adjustment out) is a non-sales stock reduction with no
        # dedicated canonical/sanity slot — fold it into purchase_return so the stock
        # identity (closing = opening + purchase + purchase_free + s_return -
        # purchase_return - sales - sales_free) stays exact (JACKSON GA 12 CREAM:
        # 21+40+2-40-13-2=8).
        rec["purchase_return"] = col.get("purchase_return", 0.0) + col.get("_stkout", 0.0)
        if not any(rec[k] for k in _EMIT_KEYS):
            continue
        records.append(rec)
    return records
