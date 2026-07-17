"""JAY AMBE MEDICAL AGENCY 'Monthly Stock & Sales Statement' (Marg/KLM, DHANERA).

Sibling of marg_monthly_ss_statement_pdf (AAKASH), but the SHORT variant: it stops
at the Balance column — there are NO trailing Order1 / Order2 / Remarks columns, so
the AAKASH gate ('goodstotalsalepurc.ret.balance' + 'order1order2remarks') never
fires and the file falls through to the coarse 'stock & sales' -> simple4 rule, which
collapses the 5..7 variable-fill numeric cells positionally (Total -> sales_qty,
Sale -> closing) and lands 100% RED / SANITY_FAILED.

Banded by 'Make : <DIV>'. Column header (two visual rows — labels on one `top`, the
'Qty' sub-labels on the next):

  Code | Product | Pack | Opening | Purchase | Goods Ret. In. | Total | Sale |
        Purc. Ret. | Balance

Gate token (compact, spaces stripped, lowercased): a header run UNIQUE to this export
    'openingpurchasegoodsret.totalsalepurc.ret.balance'
plus the report title 'monthlystock&salesstatement'. AAKASH's compact run is
'...goodstotalsale...' (its 'Goods Ret.' + 'Total In' wrap so 'ret.' drops between
'goods' and 'total') and it additionally carries 'order1order2remarks', so neither
side can steal the other.

Reconciliation (verified on every qty row AND the per-division 'Total value :' control
rows): Balance = Opening + Purchase + GoodsRet - Sale - PurcRet. 'Total' (=Opening+
Purchase+GoodsRet) is a DERIVED column and is NOT mapped to any movement field.
Goods Ret. In. = goods returned by customers (an inflow -> sales_return, +); Purc. Ret.
= purchase return (an outflow -> purchase_return, -).

Blank interior cells collapse in the PDF text layer, so the numeric-word count per row
varies (3..5). We read word x-positions, anchor on the printed header labels' RIGHT
edges (the 7 numeric columns are right-aligned so a 2-digit qty and a long value-total
share the same right edge), and bucket each numeric word into its column by the midpoint
between consecutive right edges. The per-page address / 'Year :' / 'Page N of N' /
'Period :' / 'Make :' / division-total lines are skipped.
"""
import io
import re

_NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*$")
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
    anchors for the 7 right-aligned numeric columns; else None."""
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
        "goods_ret": x1["Goods"],   # Goods Ret. In. (customer returns -> sales_return, +)
        "total_in": x1["Total"],    # DERIVED, ignored
        "sale": x1["Sale"],
        # Purc. Ret. right edge: the 'Ret.' word that belongs to Purc. (right of Sale).
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


_COL_ORDER = ["opening", "purchase", "goods_ret", "total_in", "sale", "purc_ret", "balance"]

# name-column values that are NOT product rows (band / totals / header echo / footer /
# per-page address+meta banner). Matched case-insensitively on the joined left-of-name
# text.
_SKIP_NAME_RE = re.compile(
    r"^(make\b|page\b|period\b|total\b|grand\b|company\b|phone|gstin|mobile|"
    r"opening|purchase|balance|remarks|code\b|year\b|monthly\b|email|"
    r"jay\b|no\.|authorized|admin|note\b|rpt|"
    # street/address fragments of this vendor's per-page banner
    r"\d*-?dharnidhar|shoping|centre|bus\b|staion|road\b|dhanera|dharnidhar)",
    re.I,
)
_LEGEND_RE = re.compile(
    r"near expiry|short supplied|non moving|hospital|challan|include|valuation|"
    r"adjustment|inward|opening qty|sale qty|effective rate|signatory|"
    r"^[#?!*&]\s", re.I
)


def parse_jayambe_monthly_ss_balance(text, file_bytes=None):
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
                    bounds = []
                    for i in range(len(xs) - 1):
                        bounds.append((xs[i] + xs[i + 1]) / 2.0)
                    name_cut = anchors["opening"] - 34
                    balance_right = anchors["balance"] + (anchors["balance"] - anchors["purc_ret"]) / 2.0
                    continue
                if not anchors:
                    continue

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

                if not left_text:
                    continue
                if _SKIP_NAME_RE.match(low) or "value :" in low or "make :" in low:
                    continue
                if _LEGEND_RE.search(low):
                    continue
                if not nums:
                    continue

                col = {}
                for rx, t in nums:
                    idx = 0
                    while idx < len(bounds) and rx >= bounds[idx]:
                        idx += 1
                    key = _COL_ORDER[idx]
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

                toks = [w["text"] for w in left_words if w["text"] != "*"]
                # strip leading Code token (contains a digit, e.g. HBSO01 / GA 101)
                if toks and any(c.isdigit() for c in toks[0]):
                    toks = toks[1:]
                name = " ".join(toks).strip()
                if not name:
                    continue

                records.append({
                    "product_name": name,
                    "opening_stock": opening,
                    "purchase_stock": purchase,
                    "sales_return": goods_ret,    # Goods Ret. In. (customer returns, +)
                    "sales_qty": sale,
                    "purchase_return": purc_ret,  # Purc. Ret. (purchase return, -)
                    "closing_stock": balance,
                })
    return records
