"""Marg 'STOCK & SALES ANALYSIS' movement detail — SPARSE (blank-omitted) variant.

Same two-line header and column set as the dense ``marg_movement_detail`` layout
used by the AHUJA MEDICAL AGENCY family::

    ITEM DESCRIPTION | OPENING STOCK | PURCHASES | REPL./RETURN | OTHERS |
    TOTAL STOCK | SALES | REPL./RETURN | OTHERS | CLOSING STOCK | RATE

CRITICAL DIFFERENCE (AMIT MEDICOS): this vendor's PDF OMITS zero-value cells
(prints them blank), so a data row carries a *variable* number of tokens (4-7 incl.
rate) instead of a fixed 9. A flat token-count parse (which the dense parser uses)
therefore mis-aligns every sparse row. We instead read word x-positions with
pdfplumber and bucket each number under its header column using the printed
sub-label row (STOCK PURCHASES RETURN OTHERS STOCK SALES RETURN OTHERS STOCK RATE)
as the anchor, so blanks stay blank and every value lands in the right column.

Column identity (verified against the printed group subtotals):
    TOTAL   = OPENING + PURCHASES + pur REPL/RETURN + pur OTHERS   (all additive)
    CLOSING = TOTAL   - SALES     - sale REPL/RETURN - sale OTHERS

Canonical mapping — fold the secondary inflow columns (pur REPL/RETURN, pur OTHERS)
into ``purchase_free`` and the secondary outflow columns (sale REPL/RETURN, sale
OTHERS) into ``sales_free`` (the marg_open_pur_free_sale / pharmassist_mfac
precedent). We compute those folds off the ERP's own printed TOTAL so the row
reconciles exactly regardless of the individual columns being blank:
    purchase_free = TOTAL - OPENING - PURCHASES     (secondary inflows)
    sales_free    = TOTAL - CLOSING - SALES         (secondary outflows)
Then closing = opening + purchase_stock + purchase_free - sales_qty - sales_free
holds exactly (matches core.sanity: op+pur+pf-pr-sal-sf+sr).
"""
import io
import re

from extractors.stock_pdf.parse_common import _zero_row_is_product

_NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*$")

# Header sub-label token that is unique enough to lock onto this bottom header line.
_HEADER_TOKENS = ("PURCHASES", "SALES", "RATE", "OTHERS", "RETURN")

# Column identities in printed left-to-right order (the two duplicate STOCK/RETURN/
# OTHERS labels are disambiguated by position when building the anchors below).
_COL_ORDER = [
    "opening",       # OPENING STOCK
    "purchases",     # PURCHASES
    "pur_return",    # REPL./RETURN  (purchase side)
    "pur_others",    # OTHERS        (purchase side)
    "total",         # TOTAL STOCK
    "sales",         # SALES
    "sale_return",   # REPL./RETURN  (sale side)
    "sale_others",   # OTHERS        (sale side)
    "closing",       # CLOSING STOCK
    "rate",          # RATE
]

_NAME_CUT = 260.0   # product name / pack live left of the first numeric column

# Tokens that only ever appear in the vendor / address / title / footer block that
# Marg re-prints at the top of every continuation page. Used (generically, not per
# vendor) to stop such a text-only line being folded into the previous product name.
_HEADER_NOISE_RE = re.compile(
    r"\b(agenc|medico|medical|pharmaceutical|pharmac|distribut|enterpris|"
    r"trader|gstin|phone|e-mail|email|store|analysis|description|continued|"
    r"bazar|complex|floor|nagar|ward\s+no|gunj|sadak|super\s+market)"
    r"|[&@]|stock\s*&\s*sales",
    re.I,
)


def _is_header_noise(name):
    return bool(_HEADER_NOISE_RE.search(name))


def _is_num(t):
    t = t.replace(",", "")
    return bool(_NUM_RE.fullmatch(t)) and any(c.isdigit() for c in t)


def _to_f(t):
    try:
        return float(t.replace(",", ""))
    except ValueError:
        return 0.0


def _header_anchors(words):
    """If this word row is the bottom sub-label header, return the 10 column x-centres.

    The sub-label line reads: STOCK PURCHASES RETURN OTHERS STOCK SALES RETURN OTHERS
    STOCK RATE. STOCK/RETURN/OTHERS each repeat, so we map by ordered position rather
    than by name.
    """
    texts = [w["text"] for w in words]
    if not all(tok in texts for tok in _HEADER_TOKENS):
        return None
    # Must have the exact repeating shape (3 STOCK, 2 PURCHASES-region RETURN/OTHERS).
    if texts.count("STOCK") < 3 or texts.count("RETURN") < 2 or texts.count("OTHERS") < 2:
        return None
    seq = [(w["text"], (w["x0"] + w["x1"]) / 2.0) for w in words]
    # Expected label sequence, left-to-right, for the 10 numeric columns.
    expected = ["STOCK", "PURCHASES", "RETURN", "OTHERS", "STOCK", "SALES",
                "RETURN", "OTHERS", "STOCK", "RATE"]
    # Greedily consume the expected labels in order.
    centres, i = [], 0
    for label, cx in seq:
        if i < len(expected) and label == expected[i]:
            centres.append(cx)
            i += 1
    if i != len(expected):
        return None
    return dict(zip(_COL_ORDER, centres))


def _boundaries(anchors):
    """Midpoints between consecutive column centres -> bucket boundaries."""
    centres = [anchors[c] for c in _COL_ORDER]
    return [(centres[i] + centres[i + 1]) / 2.0 for i in range(len(centres) - 1)]


def _cluster_rows(words, tol=4):
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


def _bucket(cx, boundaries):
    """Return the column index (0..9) for a number whose centre is cx."""
    for i, b in enumerate(boundaries):
        if cx < b:
            return i
    return len(boundaries)


def parse_marg_movement_detail_sparse(text, file_bytes=None):
    if not file_bytes:
        return []
    import pdfplumber

    records = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        anchors = None
        boundaries = None
        for page in pdf.pages:
            words = page.extract_words()
            for row_words in _cluster_rows(words):
                row_words = sorted(row_words, key=lambda w: w["x0"])
                found = _header_anchors(row_words)
                if found:
                    anchors = found
                    boundaries = _boundaries(found)
                    continue
                if not anchors:
                    continue

                name_toks, pack_toks, col = [], [], {}
                for w in row_words:
                    t = w["text"]
                    # drop the horizontal separator rules ("-----" runs) that the
                    # text layer emits between groups / at page edges.
                    if set(t) == {"-"} and len(t) >= 3:
                        continue
                    cx = (w["x0"] + w["x1"]) / 2.0
                    if _is_num(t) and cx >= _NAME_CUT - 5:
                        idx = _bucket(cx, boundaries)
                        # only first number wins a column (guard duplicate glyphs)
                        col.setdefault(_COL_ORDER[idx], _to_f(t))
                    elif w["x0"] < 185:
                        name_toks.append(t)
                    elif w["x0"] < _NAME_CUT:
                        pack_toks.append(t)

                name = " ".join(name_toks).strip()
                low = name.lower()

                # Subtotal / grand-total / footer / page-header re-print rows -> skip
                # and break any name-wrap carry. These are always LEFT-anchored label
                # rows ("Quantity ...", "Value in Rs. ...", "Total Quantity ...",
                # page footers), so match on the row PREFIX. A substring test would
                # wrongly drop genuine products whose name contains the word (e.g.
                # "EXTEND TOTAL TAB").
                if (not name and not col):
                    continue
                if low.startswith((
                        "quantity", "value in rs", "total quantity", "total value",
                        "page", "continued", "item description", "store :", "store:",
                        "stock & sales", "stock and sale", "gstin", "phone",
                        "e-mail")):
                    continue
                # vendor / address / title re-print block at the top of a page.
                if _is_header_noise(name):
                    continue
                # division band line like "KLM (COSMO Q)" — text, no numbers.
                if name.upper().startswith("KLM") and not col:
                    continue

                has_nums = bool(col)
                if not has_nums:
                    # name-only continuation of the previous product (wrapped long
                    # name). Only fold a short, genuine alphabetic fragment — never a
                    # separator remnant or a page-header/footer re-print line.
                    if (name and not pack_toks and records
                            and any(c.isalpha() for c in name)
                            and len(name_toks) <= 4
                            and not _is_header_noise(name)):
                        records[-1]["product_name"] = (
                            records[-1]["product_name"] + " " + name).strip()
                    continue
                if not name:
                    continue

                opening = col.get("opening", 0.0)
                purchases = col.get("purchases", 0.0)
                total = col.get("total", 0.0)
                sales = col.get("sales", 0.0)
                closing = col.get("closing", 0.0)

                # Keep genuine zero-activity catalog SKUs: a named product with no
                # movement this period (often only a rate printed). Only drop a
                # nameless / address phantom.
                if opening == 0 and purchases == 0 and total == 0 and \
                        sales == 0 and closing == 0 and \
                        not _zero_row_is_product(name):
                    continue

                # Fold secondary movement columns off the ERP's printed TOTAL so the
                # row reconciles exactly even when interior cells are blank.
                purchase_free = total - opening - purchases   # pur REPL/RETURN+OTHERS
                sales_free = total - closing - sales          # sale REPL/RETURN+OTHERS

                records.append({
                    "product_name": name,
                    "pack": " ".join(pack_toks).strip(),
                    "opening_stock": opening,
                    "purchase_stock": purchases,
                    "purchase_free": purchase_free,
                    "sales_qty": sales,
                    "sales_free": sales_free,
                    "closing_stock": closing,
                    "rate": col.get("rate", 0.0),
                })
    return records
