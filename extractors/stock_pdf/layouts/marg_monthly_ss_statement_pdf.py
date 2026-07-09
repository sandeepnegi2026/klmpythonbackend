"""Marg/KLM PALANPUR 'MONTHLY STOCK & SALES STATEMENT' (AAKASH DISTRIBUTORS).

Banded by Make/division (KLCOSMOCOR, KLDERMACOR, ...). Column header (two visual
rows — main labels on one `top`, the "Qty/Free/Ret." sub-labels on the next):

  Code | * | Product | Pack | Opening | Purchase | Goods Ret. | Total In |
        Sale | Purc. Ret. | Balance | Order 1 (Qty/Free) | Order 2 (Qty/Free) | Remarks

Reconciliation (verified on qty rows AND the per-division "Total value :-" control
rows):
    Balance = Opening + Purchase + GoodsRet - Sale - PurcRet
so GoodsRet (goods returned by customers) is a sales_return-style inflow (+) and
Purc. Ret. is a purchase_return outflow (-). "Total In" (= Opening+Purchase+GoodsRet)
is a DERIVED column and must NOT be mapped to any movement field. Order1/Order2
Qty+Free and Remarks are ordering hints, ignored.

Blank interior cells collapse in the PDF text layer, so the count of numeric words per
row varies (3..7) and flat trailing-N slicing mis-aligns columns. We read word
x-positions with pdfplumber, take the printed header labels' RIGHT edges (x1) as column
anchors (the 7 numeric columns are right-aligned, so every value in a column — 2-digit
qty or long value-total — shares its right edge), and bucket each numeric word into its
column by the midpoint between consecutive column right edges. The leading Code token is
stripped from the product name; the per-division "Total value :-" rows are skipped.
"""
import io
import re

_NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*$")
# tokens that uniquely identify this export's header row
_HEADER_TOKENS = ("Opening", "Purchase", "Goods", "Total", "Sale", "Balance")


def _is_num(t):
    t = t.replace(",", "")
    return bool(_NUM_RE.fullmatch(t)) and any(c.isdigit() for c in t)


def _to_f(t):
    try:
        return float(t.replace(",", ""))
    except ValueError:
        return 0.0


def _header_anchors(words):
    """If this word row is the main column-label header, return column x1 (right-edge)
    anchors.

    The 7 numeric columns are RIGHT-aligned, so each number's right edge (x1) is a
    stable per-column anchor regardless of digit count (a value-total's long number
    and a 2-digit qty share the same right edge). Header labels are left-/centre-set
    and sit ~5-14 px left of the data right edge, so we anchor on the label right edge
    and bucket each number by the midpoint between consecutive label right edges — the
    ~40 px inter-column gaps leave ample margin. Columns kept: Opening, Purchase,
    Goods Ret., Total In (derived, ignored), Sale, Purc. Ret., Balance. Anything to the
    right of Balance is Order1/Order2/Remarks and is ignored.
    """
    x1 = {}
    for w in words:
        x1.setdefault(w["text"], w["x1"])
    if not all(tok in x1 for tok in _HEADER_TOKENS):
        return None
    if "Purc." not in x1:
        return None
    anchors = {
        "opening": x1["Opening"],
        "purchase": x1["Purchase"],
        "goods_ret": x1["Goods"],   # Goods Ret. (customer returns -> sales_return, +)
        "total_in": x1["Total"],    # DERIVED, ignored
        "sale": x1["Sale"],
        # Purc. Ret. right edge: use the "Ret." that belongs to Purc. (right of Sale).
        # Fall back to the "Purc." word if the paired Ret. is missing.
        "purc_ret": max((w["x1"] for w in words
                         if w["text"] == "Ret." and w["x1"] > x1["Sale"]),
                        default=x1["Purc."] + 22),
        "balance": x1["Balance"],
    }
    return anchors


def _cluster_rows(words, tol=6):
    by_top = {}
    for w in words:
        by_top.setdefault(round(w["top"]), []).append(w)
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


# ordered movement columns and their canonical target (None = derived/ignore)
_COL_ORDER = ["opening", "purchase", "goods_ret", "total_in", "sale", "purc_ret", "balance"]

_SKIP_NAME_RE = re.compile(
    r"^(make\b|page\b|period\b|total\b|grand\b|company\b|phone|gstin|"
    r"opening|purchase|balance|remarks|code\b)", re.I
)
# footer legend lines (marker glyphs + phrases) carry a stray number (e.g. "last 60
# days") that would otherwise bucket into a movement column.
_LEGEND_RE = re.compile(
    r"near expiry|short supplied|non moving|hospital|challan|include|"
    r"^[#?!*&]\s", re.I
)


def parse_marg_monthly_ss_statement_pdf(text, file_bytes=None):
    if not file_bytes:
        return []
    import pdfplumber

    records = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        anchors = None
        bounds = None
        name_cut = None
        balance_right = None
        for page in pdf.pages:
            words = page.extract_words()
            for row_words in _cluster_rows(words):
                row_words = sorted(row_words, key=lambda w: w["x0"])
                found = _header_anchors(row_words)
                if found:
                    anchors = found
                    xs = [anchors[c] for c in _COL_ORDER]
                    # midpoint boundaries between consecutive column right edges
                    bounds = []
                    for i in range(len(xs) - 1):
                        bounds.append((xs[i] + xs[i + 1]) / 2.0)
                    # numbers begin left of the Opening right edge; the Pack column
                    # sits well left of the first numeric column.
                    name_cut = anchors["opening"] - 34
                    # right cut-off: anything past the Balance right edge is
                    # Order1/Order2/Remarks and must be ignored.
                    balance_right = anchors["balance"] + (anchors["balance"] - anchors["purc_ret"]) / 2.0
                    continue
                if not anchors:
                    continue

                # split words into name/pack (left of name_cut) and numeric cells.
                # Bucket numbers by their RIGHT edge (x1) — right-aligned columns.
                nums = []
                left_words = []
                for w in row_words:
                    cx = (w["x0"] + w["x1"]) / 2.0
                    if _is_num(w["text"]) and w["x1"] > name_cut and w["x1"] <= balance_right:
                        nums.append((w["x1"], w["text"]))
                    elif cx < name_cut:
                        left_words.append(w)

                left_text = " ".join(w["text"] for w in left_words).strip()
                low = left_text.lower()

                # division band / totals / header-echo / footer -> skip
                if not left_text:
                    continue
                if _SKIP_NAME_RE.match(low) or "value :" in low or "make :" in low:
                    continue
                if _LEGEND_RE.search(low):
                    continue

                if not nums:
                    # name-only line with no numbers (band echo / wrap) -> skip
                    continue

                # bucket each number to its column by right-edge boundaries
                col = {}
                for rx, t in nums:
                    idx = 0
                    while idx < len(bounds) and rx >= bounds[idx]:
                        idx += 1
                    key = _COL_ORDER[idx]
                    # keep the last write per column (right-most wins on ties)
                    col[key] = _to_f(t)

                opening = col.get("opening", 0.0)
                purchase = col.get("purchase", 0.0)
                goods_ret = col.get("goods_ret", 0.0)
                sale = col.get("sale", 0.0)
                purc_ret = col.get("purc_ret", 0.0)
                balance = col.get("balance", 0.0)

                if (opening == 0 and purchase == 0 and goods_ret == 0
                        and sale == 0 and purc_ret == 0 and balance == 0):
                    continue

                # product name/pack: strip leading Code token, drop the '*' marker
                toks = [w["text"] for w in left_words if w["text"] != "*"]
                # leading code token: first token contains a digit or is all-caps+digit
                if toks and any(c.isdigit() for c in toks[0]):
                    toks = toks[1:]
                # pack is the right-most left-column token(s); keep it simple —
                # pipeline's extract_pack_from_product will re-split, so join all.
                name = " ".join(toks).strip()
                if not name:
                    continue

                records.append({
                    "product_name": name,
                    "opening_stock": opening,
                    "purchase_stock": purchase,
                    "sales_return": goods_ret,   # Goods Ret. (customer returns, +)
                    "sales_qty": sale,
                    "purchase_return": purc_ret,  # Purc. Ret. (purchase return, -)
                    "closing_stock": balance,
                })
    return records
