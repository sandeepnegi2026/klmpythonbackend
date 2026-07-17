"""Prompt ERP 'Stock Statement (Datewise)' — free-carrying KLM variant (V.G.RAJA).

Powered By: PROMPT. Banded by division (e.g. "KLM LABORATORIES PVT LTD  KLM COSMO Q").
Two-row column header:
    group row:  Product Name | Pack | OpStk | Pur | Sales | ClStk
    sub  row:   Qty | Qty  Free | Qty  Free  mount | Qty  Amount | A3Mn | E/E | Age

Each data line = serial index + product + pack + an 8-value numeric core
(OpStk.Qty, Pur.Qty, Pur.Free, Sales.Qty, Sales.Free, Sales.Amount,
 ClStk.Qty, ClStk.Amount) + A3Mn + optional E/E(expiry) + Age.

Free qty is carried in dedicated Pur.Free and Sales.Free columns. The generic
`prompt` text parser assumes a 7-value tail (OpStk,Pur,Sales,Free,_,ClStk,Amount)
and reads the closing *Amount* into closing_stock — wrong for this variant.
Reconciles as ClStk.Qty = OpStk.Qty + Pur.Qty - Sales.Qty
(e.g. BLEMGUARD-TX 19+0-1=18=ClStk.Qty; 508 is the Sales.Amount, not closing).

Interior columns are frequently BLANK and the text layer splits a product across
two ~1px-apart `top` values (serial+numbers on one visual line, the product/pack on
another), so a flat token parse mis-columns rows. We read word x-positions with
pdfplumber, cluster words into visual rows, derive column centres from the printed
sub-header, and bucket each numeric token to its nearest core column (dropping the
trailing A3Mn / E/E / Age stats).
"""
import io
import re

_NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*$")
# sub-header tokens, in printed left-to-right order, mapped to the 9 core anchors
# (the 9th, A3Mn, is only used as a right boundary — its value is discarded).
_SUB_TOKENS = ("Qty", "Qty", "Free", "Qty", "Free", "mount", "Qty", "Amount", "A3Mn")
_CORE_KEYS = (
    "opening_stock",     # OpStk.Qty
    "purchase_stock",    # Pur.Qty
    "purchase_free",     # Pur.Free
    "sales_qty",         # Sales.Qty
    "sales_free",        # Sales.Free
    "sales_value",       # Sales.Amount
    "closing_stock",     # ClStk.Qty
    "closing_stock_value",  # ClStk.Amount
)
_NAME_MAX_X = 145        # product-name words live left of the Pack column (~148)
_PACK_MAX_X = 190        # pack words live between name and the OpStk numbers (~191)


def _is_num(t):
    return bool(_NUM_RE.fullmatch(t.replace(",", ""))) and any(c.isdigit() for c in t)


def _to_f(t):
    try:
        return float(t.replace(",", ""))
    except ValueError:
        return 0.0


def _cluster_rows(words, tol=6):
    """Group words into visual rows: tops within `tol` px of the cluster's first
    top belong together (folds the 1-2 px sub-line jitter that splits a product)."""
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


def _sub_header_centres(row_words):
    """If this word-row is the numeric sub-header (Qty Qty Free Qty Free mount Qty
    Amount A3Mn ...), return the 9 column x-centres in print order, else None."""
    ws = sorted(row_words, key=lambda w: w["x0"])
    texts = [w["text"] for w in ws]
    # locate the 9-token core sequence anywhere in the row
    n = len(_SUB_TOKENS)
    for i in range(0, len(texts) - n + 1):
        if texts[i:i + n] == list(_SUB_TOKENS):
            seg = ws[i:i + n]
            return [(w["x0"] + w["x1"]) / 2.0 for w in seg]
    return None


_SKIP_NAME_RE = re.compile(
    r"^(total|bills?|for,|partner|powered|page|product\s+name|m/s|shop|phone|"
    r"junagadh|from:|stock\s+statement|l/sale)",
    re.I,
)
_DIVISION_RE = re.compile(r"^KLM\s+LABORAT", re.I)


def parse_prompt_dstk_free_pdf(text, file_bytes=None):
    if not file_bytes:
        return []
    import pdfplumber

    records = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        centres = None
        a3mn_left = None
        for page in pdf.pages:
            words = page.extract_words()
            for row_words in _cluster_rows(words):
                found = _sub_header_centres(row_words)
                if found:
                    centres = found[:8]          # 8 core columns
                    a3mn_left = found[8] - 12.0   # left edge of A3Mn boundary
                    continue
                if not centres:
                    continue

                name_toks, pack_toks = [], []
                col = {}
                for w in sorted(row_words, key=lambda w: w["x0"]):
                    cx = (w["x0"] + w["x1"]) / 2.0
                    if _is_num(w["text"]) and cx >= (centres[0] - 20) and cx < a3mn_left:
                        # bucket to the nearest core column centre
                        j = min(range(8), key=lambda k: abs(cx - centres[k]))
                        col[j] = _to_f(w["text"])
                    elif w["x0"] < _NAME_MAX_X:
                        # leading serial index is a bare int at the far left; drop it
                        if w["x0"] < 40 and w["text"].isdigit():
                            continue
                        name_toks.append(w["text"])
                    elif w["x0"] < _PACK_MAX_X:
                        pack_toks.append(w["text"])

                name = " ".join(name_toks).strip()
                low = name.lower()

                # division band / footer / repeated header -> break any name-wrap carry
                if _DIVISION_RE.match(name) or _SKIP_NAME_RE.match(low):
                    continue

                if not col:
                    # a name-only continuation of the previous product (wrapped name).
                    # Only carry alphabetic continuations — reject stray Bills/date/code
                    # footer tokens (e.g. "CE/26-27/02569") that fall in the name band.
                    if (
                        name
                        and not pack_toks
                        and records
                        and all(t[:1].isalpha() and "/" not in t for t in name_toks)
                    ):
                        records[-1]["product_name"] = (
                            records[-1]["product_name"] + " " + name).strip()
                    continue

                if not name:
                    continue

                # drop all-zero phantom rows
                if not any(col.get(k, 0.0) for k in range(8)):
                    continue

                r = {"product_name": name, "pack": " ".join(pack_toks).strip()}
                for k in range(8):
                    r[_CORE_KEYS[k]] = col.get(k, 0.0)
                records.append(r)

    return records
