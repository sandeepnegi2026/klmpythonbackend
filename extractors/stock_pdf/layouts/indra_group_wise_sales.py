"""INDRA DRUG HOUSE "Group Wise Sales" stock-and-sales statement (KLM divisions).

Single-vendor KLM-flavoured report exported by INDRA DRUG HOUSE. The title line is
glued (spaces stripped) as:

    GroupWiseSales(From01/05/2026UpTo31/05/2026)

The grid has a TWO-ROW column header. The two text columns (Product Name, Strength)
carry no number; the remaining 11 header cells are all numeric. The header reprints
per page (and once more as a trailing footer header before the "DUMP STOCK" note),
and rows are grouped under a division band like:

    KLMPHARMADIVISION (KLMP0)

Header (row1 / row2) -> 11 numeric columns, left to right:

    Opening  | Opening | Purchase | Purchase | Total | Issue | Issue | Closing | Closing | Dump  | Near
    Stock    | Value   | Qty      | Value    | Qty   | Qty   | Value | Qty     | Value   | Stock | Expiry

Column -> canonical mapping:
    Opening Stock  -> opening_stock
    Opening Value  -> opening_value
    Purchase Qty   -> purchase_stock
    Purchase Value -> purchase_value
    Total Qty      -> DROPPED  (derived = Opening + Purchase; NOT a canonical field)
    Issue Qty      -> sales_qty
    Issue Value    -> sales_value
    Closing Qty    -> closing_stock
    Closing Value  -> closing_stock_value   (rupees, NOT the qty)
    Dump Stock     -> exp_damage            (near-expiry / dump quantity)
    Near Expiry    -> DROPPED               (always 0.00 in samples; a value, not a qty)

Why POSITIONAL: several columns are 0 and print as bare '0' or '0.00', but a couple
of value cells can be blank/absent in other exports and the qty/value pairs can glue.
Numbers are RIGHT-aligned to fixed x positions, so each number is bucketed into its
column by matching its right edge (x1) to the sub-header label's right edge. The two
text columns are split off by an x threshold derived from the "Strength" header.

Reconcile identity (verified on all 8 rows of the sample, e.g.
SOFIRASH 59 opening - 36 issue = 23 closing; every other row 0 issue so
closing == opening):

    closing_stock == opening_stock + purchase_stock - sales_qty

which is exactly the postprocess sanity identity with purchase_free / purchase_return
/ sales_free / sales_return all zero. Printed group Total oracle (KLM PHARMA DIVISION):
Opening 223, Opening Value 17,472.88, Issue Qty 36, Issue Value 3,792, Closing Value
14,001, Dump 140 -- the emitted rows sum to these to the paisa.
"""
import io

import pdfplumber

# sub-header (second header row) token stream: the 11 numeric-column labels in order.
_SUBHEADER_TOKENS = ["Stock", "Value", "Qty", "Value", "Qty",
                     "Qty", "Value", "Qty", "Value", "Stock", "Expiry"]

# sub-header label -> canonical field, paired by ORDER with _SUBHEADER_TOKENS.
# "_total" and "_near" are parsed for bucketing but dropped before emit.
_SUBHEADER_SEQUENCE = [
    "opening_stock",         # Opening Stock
    "opening_value",         # Opening Value
    "purchase_stock",        # Purchase Qty
    "purchase_value",        # Purchase Value
    "_total",                # Total Qty (derived = Opening + Purchase; DROP)
    "sales_qty",             # Issue Qty
    "sales_value",           # Issue Value
    "closing_stock",         # Closing Qty
    "closing_stock_value",   # Closing Value
    "exp_damage",            # Dump Stock
    "_near",                 # Near Expiry (value; DROP)
]

# emitted canonical fields (in a stable order)
_EMIT_FIELDS = [
    "opening_stock", "opening_value",
    "purchase_stock", "purchase_value",
    "sales_qty", "sales_value",
    "closing_stock", "closing_stock_value",
    "exp_damage",
]

_SKIP_PREFIXES = (
    "productname", "product name", "opening", "purchase", "total",
    "www.", "phone", "groupwisesales", "after90days", "page",
    "indradrughouse", "saraigajra",
)


def _is_num_token(t):
    s = t.replace(",", "").rstrip(".")
    if s.startswith("-"):
        s = s[1:]
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
                matched = None
                for k in by_top:
                    if abs(k - key) <= 2:
                        matched = k
                        break
                by_top.setdefault(matched if matched is not None else key, []).append(w)
            for top in sorted(by_top):
                out.append((pi, sorted(by_top[top], key=lambda w: w["x0"])))
    return out


def _is_subheader(row):
    return [w["text"] for w in row] == _SUBHEADER_TOKENS


def _strength_x0(row):
    """x0 of the 'Strength' label on the main header row-1, else None. Pins the
    pack/strength column so its tokens are peeled off the product name."""
    for w in row:
        if w["text"].strip().lower() == "strength":
            return w["x0"]
    return None


def _subheader_anchors(row):
    """Map each column key to its sub-header label right edge (x1), in order."""
    return {key: w["x1"] for key, w in zip(_SUBHEADER_SEQUENCE, row)}


def _num_x0_from_anchors(anchors):
    """Left boundary of the numeric band = a bit left of the first (opening_stock)
    anchor's right edge. Product/Strength text never crosses it (Strength header
    ends ~165; first number right edge ~194)."""
    first = anchors["opening_stock"]
    return first - 30.0


def _bucket_numbers(nums, anchors):
    """Assign each numeric word to the nearest column by right-edge distance."""
    cols = list(anchors.items())
    out = {}
    for w in nums:
        key = min(cols, key=lambda kv: abs(kv[1] - w["x1"]))[0]
        out[key] = _to_f(w["text"])
    return out


def _is_band(line_low):
    """Division/company band header, e.g. 'KLMPHARMADIVISION (KLMP0)'."""
    return "division" in line_low and "(" in line_low


def parse_indra_group_wise_sales(text, file_bytes=None):
    if not file_bytes:
        return []

    records = []
    anchors = None
    num_x0 = None
    pack_x0 = 130.0   # fallback pack/strength column left boundary
    division = None

    for _page, row in _extract_word_rows(file_bytes):
        sx = _strength_x0(row)
        if sx is not None:
            pack_x0 = sx - 8.0   # a hair left of the Strength label
        if _is_subheader(row):
            anchors = _subheader_anchors(row)
            num_x0 = _num_x0_from_anchors(anchors)
            continue

        joined = " ".join(w["text"] for w in row).strip()
        line_low = joined.lower()
        compact = joined.replace(" ", "").lower()

        # division / company band -> remember, do not emit
        if _is_band(line_low):
            division = joined.strip()
            continue

        if not line_low:
            continue
        # main header row-1 ("ProductName Strength Opening ...") re-arms on next
        # sub-header; skip footer/notes/address noise unconditionally.
        if any(compact.startswith(p) for p in
               (p.replace(" ", "") for p in _SKIP_PREFIXES)):
            continue
        if anchors is None:
            continue

        # group Total row: starts with 'Total' and has no product text -> skip
        if row and row[0]["text"].strip().lower() == "total":
            continue

        nums = [w for w in row
                if w["x0"] >= num_x0 and _is_num_token(w["text"])]
        name_toks = [w["text"] for w in row if w["x0"] < pack_x0]
        pack_toks = [w["text"] for w in row
                     if pack_x0 <= w["x0"] < num_x0]

        name = " ".join(name_toks).strip()
        pack = " ".join(pack_toks).strip()
        if not name or not nums:
            continue

        col = _bucket_numbers(nums, anchors)

        rec = {"product_name": name, "pack": pack}
        if division:
            rec["division"] = division
        for f in _EMIT_FIELDS:
            rec[f] = col.get(f, 0.0)

        # drop fully-empty rows (all movement/closing cells 0)
        if not any(rec[f] for f in _EMIT_FIELDS):
            continue

        records.append(rec)

    return records
