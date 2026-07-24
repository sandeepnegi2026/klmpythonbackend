"""KLM 'Stock And Sales Report(Month)' — TotS/Sale_Val dialect (VASAN MEDICAL).

Sibling of ``klm_stock_sales_month`` / ``_repq`` / ``_rcpt`` / ``_netstock``: the
same KLM per-division export family (one report per division: COSMO, COSMO-Q,
COSMOCOR, DERMA, DERMACOR, PEDIA, PHARMA KLM LABORATORIES), a distinct column
vocabulary. Header row (single line):

  ProductName | Pack | Op.Qt | Purch | Free | AprP_ | MayL_ | C_Sal | Free |
  Repl | Adj | Tot.S | Sale_Val

Column semantics / canonical mapping (proven by the printed column-subtotal row
and the printed rupee grand-total row on every file):

  Op.Qt    -> opening_stock        (opening quantity)
  Purch    -> purchase_stock       (purchase inflow qty)
  Free (1) -> purchase_free        (free goods received on purchase)
  AprP_    -> ignored              (prior-period purchase, informational)
  MayL_    -> ignored              (prior-period / last-month sales, informational)
  C_Sal    -> sales_qty            (current-month sales qty, outflow)
  Free (2) -> sales_free           (free goods given out, outflow)
  Repl     -> purchase_return      (replacement returned, folded as outflow)
  Adj      -> signed adjustment    (+Adj -> purchase_free ; -Adj -> sales_free)
  Tot.S    -> closing_stock        (printed closing/total stock qty)
  Sale_Val -> sales_value          (current-month sales rupee value)

``AprP_``/``MayL_`` are the two DYNAMIC previous-month columns (they rename every
month); they are anchored positionally between ``Free`` (purch) and ``C_Sal`` and
dropped. There are TWO ``Free`` header tokens (purchase-side then sales-side); we
disambiguate by x-order, not name.

Reconciliation (COSMO JUNE): extracted column sums Purch 50, C_Sal 28, sales Free
17, Tot.S 44, Sale_Val 11442.26 == printed subtotal row `50 28 17 - - 44
11442.26`; Sale_Val sum 11442.26 == printed rupee grand total 'Sales' 11442.26.
The bottom rupee grand-total band (Op.Stk / Purchase / Sales / Closing Stk /
P.M.Sale-1 / P.M.Sale-2) is VALUE-level and is not emitted per row.

Zero-movement products print their numeric cells BLANK, so a flat left/right text
split misaligns badly (e.g. 'IMXIA F 5% 60ML 60ML 4 - - 14 7 2 2 - - - 1214.28'
has holes). All numbers are RIGHT-ALIGNED and every column's right edge lines up
with the corresponding header token's x1, so we read word x-positions with
pdfplumber and bucket each numeric word into the column whose header x1 it aligns
to (tolerance 6pt). The product name is the tokens left of the Op.Qt column.

Layout quirk (same export as the siblings): the report renders on a single page
here, but to match the family we STOP the page loop after the first page that
carries the printed rupee grand-total tail. The dashed rule lines, the division
banner (all-caps 'KLM LABORATORIES' name-only row), the column subtotal row
(blank product name), the 'Op.Stk Purchase Sales Closing Stk' value band, the
'Naveen - dd/mm/yy hh:mm' signature and the 'Document Footer Text' / 'Page x / y'
bands are all skipped by an empty/footer product name or by carrying no numbers in
the table columns.

Genuine source imbalances: a few rows (e.g. HERPIVAL — Op.Qt only, Tot.S blank;
IMXIA SOFT — closing calc 8 vs printed Tot.S 1) do not satisfy
closing == opening + purchase + purchase_free - sales - sales_free because the
vendor prints the closing (Tot.S) independently and suppresses zero cells; we
carry the vendor's printed Tot.S verbatim as closing_stock, so the printed
subtotals reconcile exactly.
"""
import io
import re

_NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*$")

# header tokens that must ALL be present for a row to be the column header
_HDR_REQUIRED = ("ProductName", "Op.Qt", "Purch", "C_Sal", "Repl", "Adj",
                 "Tot.S", "Sale_Val")
# columns in printed left-to-right order, bucketed by RIGHT edge (x1). The two
# 'Free' tokens are the purchase-side then sales-side free; disambiguated by order.
_COLS = ["Op.Qt", "Purch", "FreeP", "AprP_", "MayL_", "C_Sal", "FreeS",
         "Repl", "Adj", "Tot.S", "Sale_Val"]


def _is_num(t):
    t = t.replace(",", "")
    return bool(_NUM_RE.fullmatch(t)) and any(c.isdigit() for c in t)


def _to_f(t):
    try:
        return float(t.replace(",", ""))
    except ValueError:
        return 0.0


def _header_anchors(words):
    """If this word row is the column header, return (x1_by_col, name_cut) else None."""
    by_x = sorted(words, key=lambda w: w["x0"])
    labels = [w["text"] for w in by_x]
    if not all(t in labels for t in _HDR_REQUIRED):
        return None
    # walk left-to-right assigning each header label to a positional column;
    # the two 'Free' occurrences map to FreeP (first) then FreeS (second).
    anchors = {}
    free_seen = 0
    for w in by_x:
        t = w["text"]
        if t == "Free":
            key = "FreeP" if free_seen == 0 else "FreeS"
            free_seen += 1
            anchors[key] = w["x1"]
        elif t in ("Op.Qt", "Purch", "AprP_", "MayL_", "C_Sal", "Repl",
                   "Adj", "Tot.S", "Sale_Val"):
            anchors[t] = w["x1"]
    if "Op.Qt" not in anchors or "Tot.S" not in anchors:
        return None
    name_cut = anchors["Op.Qt"] - 24.0  # left edge of Op.Qt column ~ x0
    return anchors, name_cut


def parse_klm_stock_sales_month_tots(text, file_bytes=None):
    if not file_bytes:
        return []
    import pdfplumber

    records = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            by_top = {}
            for w in words:
                by_top.setdefault(round(w["top"]), []).append(w)

            anchors = None
            order = None
            x1s = None
            name_cut = None
            saw_grand_total = False

            for top in sorted(by_top):
                row_words = sorted(by_top[top], key=lambda w: w["x0"])
                found = _header_anchors(row_words)
                if found:
                    anchors, name_cut = found
                    order = [c for c in _COLS if c in anchors]
                    x1s = [anchors[c] for c in order]
                    continue
                if not anchors:
                    continue

                joined = "".join(w["text"] for w in row_words)
                if joined and set(joined) <= set("-"):
                    continue  # dashed rule line

                nums = [w for w in row_words
                        if _is_num(w["text"]) and (w["x0"] + w["x1"]) / 2.0 >= name_cut]
                name = " ".join(
                    w["text"] for w in row_words if w["x1"] <= name_cut
                ).strip()

                # empty-name rows: the printed rupee grand-total band carries big
                # values -> mark it (family stop condition); other empty-name rows
                # (column subtotal, footer bands) are skipped.
                if not name:
                    if nums and any(_to_f(w["text"]) >= 10000 for w in nums):
                        saw_grand_total = True
                    continue

                # A purely-numeric "name" is the rupee VALUE grand-total band whose
                # leftmost value (Op.Stk rupees, e.g. '10662.32') sits left of the
                # Op.Qt column and gets mis-read as the product name (its qty/value
                # words then leak as a phantom row). Every real product name in this
                # family contains letters, so a name with no alphabetic char is never
                # a legitimate row: treat it like the empty-name grand-total band.
                if not any(c.isalpha() for c in name):
                    if nums and any(_to_f(w["text"]) >= 10000 for w in nums):
                        saw_grand_total = True
                    continue

                low = name.lower()
                if low.startswith(("document", "page", "naveen")):
                    continue
                # division banner: name-only all-caps 'KLM LABORATORIES...' row
                if not nums and "laboratories" in low:
                    continue
                # value grand-total band label row
                if low.startswith("op.stk") or "closing stk" in low:
                    continue
                if not nums:
                    continue

                col = {}
                for w in nums:
                    xr = w["x1"]
                    best_i, best_d = None, 6.0
                    for i, xc in enumerate(x1s):
                        d = abs(xr - xc)
                        if d < best_d:
                            best_d, best_i = d, i
                    if best_i is not None:
                        col[order[best_i]] = _to_f(w["text"])

                op = col.get("Op.Qt", 0.0)
                pur = col.get("Purch", 0.0)
                fp = col.get("FreeP", 0.0)
                csal = col.get("C_Sal", 0.0)
                fs = col.get("FreeS", 0.0)
                repl = col.get("Repl", 0.0)
                adj = col.get("Adj", 0.0)
                cls = col.get("Tot.S", 0.0)
                sale_val = col.get("Sale_Val", 0.0)

                if (op == 0 and pur == 0 and fp == 0 and csal == 0 and fs == 0
                        and cls == 0 and sale_val == 0):
                    continue  # all-blank / phantom row

                # fold signed Adj so canonical closing reconciles:
                #   +Adj -> purchase_free (net inflow correction)
                #   -Adj -> sales_free    (net outflow correction)
                purchase_free = fp + (adj if adj > 0 else 0.0)
                sales_free = fs + (-adj if adj < 0 else 0.0)

                records.append({
                    "product_name": name,
                    "opening_stock": op,
                    "purchase_stock": pur,
                    "purchase_free": purchase_free,
                    "purchase_return": repl,   # replacement returned (outflow)
                    "sales_qty": csal,
                    "sales_free": sales_free,
                    "closing_stock": cls,
                    "sales_value": sale_val,
                })

            if saw_grand_total and records:
                break

    return records
