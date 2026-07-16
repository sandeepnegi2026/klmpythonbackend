"""MediVision Platinum "Stock and Sales" report — Add/Less adjustment variant
(RAJU PHARMA PARBHANI, KLM divisions).

This is a SEPARATE column layout from the SIND `medivision_stock_sales` layout.
SIND prints:   Op | Purc | Scm | Purc val | Sale | Scm | Sa val | Cl qty | Cl val
RAJU prints a WIDER movement grid with sales-return + signed-adjustment columns:

    Product name | Unit | Op | Purc | S.R. qty | S.R. val | Sale | Sa val |
                   Add qty | Less qty | Add val | Less val | Cl qty | Cl val

The flat-text header run is unique and does NOT appear in the SIND sibling
(which has no Add/Less columns):

    gate token: "salesavaladdqtylessqtyaddvallessvalclqtyclval"
    (from header line "Sale Sa valAdd qtyLess qtyAdd valLess val Cl qty Cl val")

Like the SIND sibling, this is an Adobe-UTF-8 (CID) export: pdfminer/pdfplumber
cannot map the embedded glyphs, so pdf_io falls back to PyMuPDF for `text`. The
numeric columns are RIGHT-ALIGNED and interior cells print BLANK for no-movement
products, so the flat token index cannot identify columns — we bucket each word
into its column by its RIGHT edge (x1) with PyMuPDF word coordinates.

Column right-edge (x1) bands, read off the printed header and cross-checked
against the printed grand-total footer ("Totals: 0 692762 75 71 1060074",
right edges 297/367/473/508/578 -> S.R.val / Sa val / Add val / Less val / Cl val):

    product name    : x0 < 120
    unit / pack      : 120 <= x0 < 175
    opening_stock    : x1 < 200      (Op)
    purchase_stock   : 200 <= x1 < 240   (Purc)
    S.R. qty         : 240 <= x1 < 280   (sales_return qty)
    S.R. val         : 280 <= x1 < 310
    sales_qty        : 310 <= x1 < 350   (Sale)
    sales_value      : 350 <= x1 < 390   (Sa val)
    Add qty          : 390 <= x1 < 420   (signed +  -> +sales_return slot)
    Less qty         : 420 <= x1 < 455   (signed -  -> +sales_qty slot)
    Add val          : 455 <= x1 < 490
    Less val         : 490 <= x1 < 525
    closing_stock    : 525 <= x1 < 560   (Cl qty)
    closing_value    : x1 >= 560          (Cl val)

Reconcile (verified on ~89% of rows; the remainder are genuine source
imbalances — the printed Cl val corroborates the printed Cl qty, e.g. CANROLFIN
cl qty 76 @ cl val 16924 ~= 223/u, so 76 is real and the vendor's own
opening+purchase-sale=180 simply does not tie to the printed closing 76):

    closing_stock = opening + purchase + S.R.qty + Add qty
                    - sales_qty - Less qty

Add qty is a positive stock adjustment (goods-in) -> folded into the
sales_return (+sr) slot; Less qty is a negative adjustment (goods-out) ->
folded into the sales_qty (-) slot; S.R.qty is a real sales return (+sr).

Skipped lines: the "MediVision" watermark, the repeated page header (vendor
name / address / Phone / Email / "Stock and Sales" / "Companies: ..." / date
range / "Page No. N" / the "Product name Unit Op Purc..." header), the
"Totals:" / "Generated at ..." footer, and pure product-name rows carrying NO
numeric columns (zero-stock discontinued items).
"""
import re
from collections import defaultdict

# (upper x1 bound, field name) — a numeric word whose RIGHT edge x1 < bound lands here.
_COL_BANDS = [
    (200.0, "opening_stock"),
    (240.0, "purchase_stock"),
    (280.0, "sr_qty"),
    (310.0, "sr_val"),
    (350.0, "sales_qty"),
    (390.0, "sales_value"),
    (420.0, "add_qty"),
    (455.0, "less_qty"),
    (490.0, "add_val"),
    (525.0, "less_val"),
    (560.0, "closing_stock"),
    (99999.0, "closing_stock_value"),
]

_NAME_X_MAX = 120.0   # product-name tokens (x0)
_PACK_X_MAX = 175.0   # unit / pack tokens (x0)
_NUM_X0_MIN = 175.0   # numeric columns begin after the pack column

_NUM_RE = re.compile(r"^-?\d[\d,]*\.?\d*$")

_SKIP_NAME_SUBSTR = (
    "medivision", "companies:", "stock and sales", "product name",
    "page no", "generated at", "totals", "raju pharma", "phone",
    "email", "dhanvantari", "mobile",
)


def _is_num(t):
    t = t.replace(",", "")
    return bool(_NUM_RE.fullmatch(t)) and any(c.isdigit() for c in t)


def _to_f(t):
    try:
        return float(t.replace(",", ""))
    except ValueError:
        return 0.0


def _bucket(x1):
    for bound, name in _COL_BANDS:
        if x1 < bound:
            return name
    return "closing_stock_value"


def parse_r15_medivision_stock_sales_addless(text, file_bytes=None):
    if not file_bytes:
        return []
    import fitz  # PyMuPDF — pdfminer cannot read this Adobe-UTF-8 CID export

    records = []
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        for page in doc:
            rows = defaultdict(list)
            for w in page.get_text("words"):
                rows[round(w[1])].append(w)

            for y in sorted(rows):
                row_words = sorted(rows[y], key=lambda w: w[0])

                cols = {}
                name_toks, pack_toks = [], []
                for w in row_words:
                    x0, x1, t = w[0], w[2], w[4]
                    if _is_num(t) and x0 >= _NUM_X0_MIN:
                        cols.setdefault(_bucket(x1), _to_f(t))
                    elif x0 < _NAME_X_MAX:
                        # The diagonal "MediVision" watermark occasionally lands a
                        # word inside the product-name band mid-row (e.g. "COSMOQ
                        # AC-50 MediVision"); drop just that token so the row (and
                        # its real name) survives instead of being skipped whole.
                        if t.lower() != "medivision":
                            name_toks.append(t)
                    elif x0 < _PACK_X_MAX:
                        pack_toks.append(t)

                if not cols:
                    continue

                name = " ".join(name_toks).strip().lstrip(".").strip()
                low = name.lower()
                if not name:
                    continue
                if any(s in low for s in _SKIP_NAME_SUBSTR):
                    continue

                op = cols.get("opening_stock", 0.0)
                pur = cols.get("purchase_stock", 0.0)
                srq = cols.get("sr_qty", 0.0)
                srv = cols.get("sr_val", 0.0)
                sale = cols.get("sales_qty", 0.0)
                saleval = cols.get("sales_value", 0.0)
                addq = cols.get("add_qty", 0.0)
                lessq = cols.get("less_qty", 0.0)
                cl = cols.get("closing_stock", 0.0)
                clval = cols.get("closing_stock_value", 0.0)

                # A genuine stock line carries at least one QUANTITY column; drop
                # value-only artefacts (e.g. an address/postal token that leaks
                # into a value band on the repeated page header).
                if (op == 0 and pur == 0 and srq == 0 and sale == 0
                        and addq == 0 and lessq == 0 and cl == 0):
                    continue

                records.append({
                    "product_name": name,
                    "pack": " ".join(pack_toks).strip(),
                    "opening_stock": op,
                    "purchase_stock": pur,
                    # S.R. qty (real sales return) + Add qty (positive stock
                    # adjustment / goods-in) both ADD to stock -> +sr slot.
                    "sales_return": srq + addq,
                    "sales_return_value": srv,
                    "sales_qty": sale,
                    "sales_value": saleval,
                    # Less qty (negative stock adjustment / goods-out) SUBTRACTS
                    # -> folded into the sales_qty (outflow) slot.
                    "sales_free": lessq,
                    "closing_stock": cl,
                    "closing_stock_value": clval,
                })
    return records
