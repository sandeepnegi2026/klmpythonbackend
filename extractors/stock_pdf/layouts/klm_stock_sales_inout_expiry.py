"""THANE MEDICAL AGENCY (KLM LAB) "STOCK AND SALES STATEMENT FOR KLM LAB (<DIV>)"
— one file per KLM division (COSMO / COSMO Q / COSMOCOR / DERMA / DERMACOR /
PED / PHARMA), produced by the vendor's "xtraRepStockAndSales" export.

Single flat table, NO party column (banding is by the division printed in the
header + a "DIVISION NAME KLM LAB (<DIV>)" sub-banner). Column order:

    Product Desc | Pkg. | Op Bal | Purc | Sale | Sal Val. | In/Out | Stk |
    Stk Val | Exp | 3M

The Exp column always prints blank in this export, so each data row carries a
fixed run of EIGHT numbers after the packing token:
    Op Bal, Purc, Sale, Sal Val., In/Out, Stk, Stk Val, 3M(expiry-in-3-months).

The product description WRAPS over 1-3 physical text lines while its numeric row
sits on the line that also carries the Pkg. token (e.g. "BLEMGUARD FACE" /
"30ML 5 10 5 2305.1 ..." / "SERUM"). The numbers are right-aligned into stable
x-columns, so we cluster words into visual rows by top, then bucket by x0 —
attaching the leading/trailing name fragments that share the row's vertical band.

Reconciliation is EXACT for every row in the sample corpus:
    Op Bal + Purc - Sale + In/Out = Stk
i.e. In/Out is a SIGNED stock adjustment printed WITH its sign (e.g. "-11").
A positive In/Out is an inflow -> purchase_free (opening + purchase +
purchase_free - sales_qty = closing); a negative In/Out is an outflow ->
sales_free (its magnitude subtracts: - sales_free). Both keep the canonical
reconcile exact without ever putting a negative number in a qty field.

Columns are mapped POSITIONALLY (no core synonyms): Op Bal->opening_stock,
Purc->purchase_stock, Sale->sales_qty, Sal Val.->sales_value, In/Out->inflow
adjustment, Stk->closing_stock, Stk Val->closing_stock_value. The value columns
(Sal Val., Stk Val) are NEVER read into a qty field. This is genuine stock data
with a Sale/Stock-Val grand total -> report_type=stock.
"""
import io
import re

_NUM_RE = re.compile(r"^-?\d[\d,]*\.?\d*$")

# The packing token sits at x0 ~91..150; the eight numeric columns begin at
# Op Bal (x0 ~200) and run to the right edge. Anything left of this is name/pack.
_PACK_X_MIN = 90.0    # a Pkg. token / trailing name fragment starts here or left
_NUM_X_MIN = 195.0    # first numeric column (Op Bal) begins ~200; guards packing
_NAME_X_MAX = 130.0   # product-desc fragments live at x0 ~30..~120


def _is_num(t):
    t = t.replace(",", "")
    return bool(_NUM_RE.fullmatch(t)) and any(c.isdigit() for c in t)


def _to_f(t):
    try:
        return float(t.replace(",", ""))
    except ValueError:
        return 0.0


def _cluster_rows(words):
    """Group words into logical product rows keyed on the numeric data line.

    The product description WRAPS: name-only fragments (e.g. "SERUM", "CR.",
    "MOISTURIZING GEL") print 5-9 px above/below the line that carries the eight
    numbers, so a naive top-bucket splits them off. We instead anchor a row on
    each line that holds the full 8-number data run, then attach every
    name-only physical line whose top is closer to THIS anchor than to any other
    anchor (and within a one-line-height window). This keeps a 3-line product
    name intact without ever merging two numeric rows."""
    by_top = {}
    for w in words:
        by_top.setdefault(round(w["top"]), []).append(w)
    tops = sorted(by_top)

    def _n_data_nums(ws):
        return sum(
            1 for w in ws if _is_num(w["text"]) and w["x0"] >= _NUM_X_MIN
        )

    anchors = [t for t in tops if _n_data_nums(by_top[t]) == 8]
    if not anchors:
        return [by_top[t] for t in tops]

    buckets = {t: list(by_top[t]) for t in anchors}
    for t in tops:
        if t in buckets:
            continue
        # attach this (non-anchor) line to the nearest anchor within 12 px
        nearest = min(anchors, key=lambda a: abs(a - t))
        if abs(nearest - t) <= 12:
            buckets[nearest].extend(by_top[t])
    return [buckets[a] for a in anchors]


def parse_klm_stock_sales_inout_expiry(text, file_bytes=None):
    if not file_bytes:
        return []
    import pdfplumber

    records = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            words = page.extract_words(x_tolerance=2, y_tolerance=2)
            for row_words in _cluster_rows(words):
                nums = []                 # (x0, value) for the 8 data columns
                name_toks, pack_toks = [], []  # (top, x0, text) preserve reading order
                for w in row_words:
                    t = w["text"]
                    x0 = w["x0"]
                    if _is_num(t) and x0 >= _NUM_X_MIN:
                        nums.append((x0, _to_f(t)))
                    elif x0 < _NAME_X_MAX:
                        # product-desc fragment (letters, or the "10"/"20"/"1" digits
                        # embedded in a name); keep top+x0 for reading-order rebuild
                        name_toks.append((round(w["top"]), x0, t))
                    elif _PACK_X_MIN <= x0 < _NUM_X_MIN:
                        pack_toks.append((round(w["top"]), x0, t))

                # Every genuine SKU row prints exactly the 8-number data run.
                # Rows with a different count are headers / banners / the two-value
                # grand-total footer / the "Sale .. Stock Val .." summary line.
                if len(nums) != 8:
                    continue

                # Rebuild the wrapped name/pack in PHYSICAL reading order (top, then
                # x0) so a 3-line description keeps its word order (else the merged
                # cluster's pure-x0 sort scrambles "BLEMGUARD FACE" / "SERUM").
                name = " ".join(t for _, _, t in sorted(name_toks)).strip()
                low = name.lower()
                if not name:
                    continue
                if (
                    low.startswith("division")
                    or low.startswith("divisionname")
                    or low.startswith("page")
                    or low.startswith("sale ")
                    or "product desc" in low
                ):
                    continue

                nums.sort(key=lambda p: p[0])
                op, purc, sale, salval, inout, stk, stkval, exp3m = (v for _, v in nums)

                # In/Out is a SIGNED stock adjustment. Positive -> inflow
                # (purchase_free: op + pur + pf - sales = closing); negative ->
                # outflow (sales_free magnitude: op + pur - sales - sf = closing).
                # Keeps the reconcile exact with no negative number in any qty cell.
                pf = inout if inout > 0 else 0.0
                sf = -inout if inout < 0 else 0.0

                # Drop fully empty rows (all measures zero) — phantom/blank lines.
                if op == 0 and purc == 0 and sale == 0 and stk == 0 and stkval == 0:
                    continue

                r = {
                    "product_name": name,
                    "pack": " ".join(t for _, _, t in sorted(pack_toks)).strip(),
                    "opening_stock": op,
                    "purchase_stock": purc,
                    "purchase_free": pf,          # In/Out inflow (positive)
                    "sales_free": sf,             # In/Out outflow (negative)
                    "sales_qty": sale,
                    "sales_value": salval,
                    "closing_stock": stk,
                    "closing_stock_value": stkval,
                    "expiry": exp3m,              # "3M" expiry-in-3-months qty
                }
                records.append(r)
    return records
