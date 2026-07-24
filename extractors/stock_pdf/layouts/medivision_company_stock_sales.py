"""MediVision Platinum "Stock and Sales" — per-COMPANY division export (JAGNATH PHARMA).

Sibling of medivision_stock_sales (the SIND DISTRIBUTORS "Companies: ..." whole-
report export), but this is MediVision's per-division dialect: the masthead carries
a singular "Company: KLM COSMO" band (one file per KLM division: COSMO / COSMOCOR /
COSMOQ / DERMA / DERMACOR / PEDIA / PHARMA) and a DIFFERENT column set that adds a
Purchase column and two prev-month sale columns. Header (glyph-mangled in the
Adobe-UTF-8 CID text layer, verified positionally against the data + footer totals):

    Product name | Unit | Op | Purc | Sale-W | Sale-Apr | Sa-Mar | Sa val | Cl qty | Cl val
                                        (prev-month sale cols)

Like the sibling this is an Adobe "Adobe-UTF-8" collection PDF: pdfminer/pdfplumber
maps enough glyphs that pdf_io does NOT trigger its PyMuPDF fallback (so `all_text`
is a usable-but-collapsed flat render), but the numeric columns are RIGHT-ALIGNED
and interior cells print BLANK for no-movement products, so the flat token index
does not identify the column. We re-read the PDF with PyMuPDF here and bucket each
number into its column by its RIGHT edge (x1) — the right edges are stable even
when interior cells are blank, whereas x0 drifts with the number's digit width.

Right-edge (x1) column bands, read off the printed header and VERIFIED by two
independent checks on every one of the 7 example files (0 mismatches):
  (1) per-row identity  opening + purchase - sales_qty = closing_stock
  (2) grand totals: sum(sales_value) and sum(closing_value) equal the printed
      "Totals:" footer (klm cosmo: 4873 / 53344, exact).

    opening_stock        : 174 <= x1 < 200   (Op)
    purchase_stock       : 205 <= x1 < 228   (Purc)
    sales_qty            : 238 <= x1 < 262   (Sale, current month)
    <prev-month sales>   : 295 <= x1 < 356   (Sale-W / Sale-Apr / Sa-Mar) -> DROPPED
    sales_value          : 360 <= x1 < 388   (Sa val)
    closing_stock        : 392 <= x1 < 414   (Cl qty)
    closing_stock_value  : 420 <= x1 < 448   (Cl val)

The prev-month sale columns (labelled Sale-W / Sale-Apr / Sa-Mar) are informational
period-history stats, NOT part of the current-month movement identity, so they are
dropped. A secondary right-side value block (x1 >= 450, its header mangled to
'NM60D/NM90D/qtyNM' glyphs) mirrors the closing figures at an alternate valuation;
it is outside every band above and therefore ignored. No purchase_free / return /
sales_free columns exist in this dialect (they stay 0), so the canonical stock
identity opening + purchase + purchase_free - purchase_return - sales_qty -
sales_free + sales_return = closing reduces to opening + purchase - sales_qty =
closing, which holds exactly.

Skipped lines: the lone "MediVision" watermark, the vendor/address/Mobile/Email
masthead, the "Stock and Sales" title, the "Company: KLM <DIV>" band, the date
range, "Page No. N", the header row, the "Totals:"/"Generated at ..." footer, and
any row carrying no quantity column (pure product-name / zero-stock discontinued
items).
"""
import re

# (lower x1 bound, upper x1 bound, field) — a number whose RIGHT edge falls in the
# band lands in that column. Gaps (262..295, 356..360, 448..) are intentionally
# left unmapped so prev-month sale cols and the secondary value block are ignored.
_COL_BANDS = [
    (174.0, 200.0, "opening_stock"),
    (205.0, 228.0, "purchase_stock"),
    (238.0, 262.0, "sales_qty"),
    (360.0, 388.0, "sales_value"),
    (392.0, 414.0, "closing_stock"),
    (420.0, 448.0, "closing_stock_value"),
]

_NAME_X_MAX = 120.0   # product-name tokens (x0 < 120)
_PACK_X_MAX = 165.0   # unit / pack tokens (120 <= x0 < 165)
_NUM_X0_MIN = 165.0   # numeric columns begin to the right of the pack column

_NUM_RE = re.compile(r"^-?\d[\d,]*\.?\d*$")

# lowered joined-name fragments that mark a masthead / header / footer / banner line
_SKIP_NAME_SUBSTR = (
    "medivision", "jagnath", "stock and sales", "product name",
    "company:", "page no", "generated at", "totals", "mobile", "email",
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
    for lo, hi, name in _COL_BANDS:
        if lo <= x1 < hi:
            return name
    return None


def parse_medivision_company_stock_sales(text, file_bytes=None):
    if not file_bytes:
        return []
    import fitz  # PyMuPDF — the Adobe-UTF-8 CID export needs positional (x1) reads

    from collections import defaultdict

    records = []
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        for page in doc:
            # words: (x0, y0, x1, y1, text, block, line, word_no)
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
                        b = _bucket(x1)
                        if b is not None:
                            cols.setdefault(b, _to_f(t))
                    elif x0 < _NAME_X_MAX:
                        name_toks.append(t)
                    elif x0 < _PACK_X_MAX:
                        pack_toks.append(t)

                # skip pure product-name rows (no numeric columns): discontinued /
                # zero-stock items
                if not cols:
                    continue

                name = " ".join(name_toks).strip().lstrip(".").strip()
                low = name.lower()
                if not name or any(s in low for s in _SKIP_NAME_SUBSTR):
                    continue

                op = cols.get("opening_stock", 0.0)
                pur = cols.get("purchase_stock", 0.0)
                sale = cols.get("sales_qty", 0.0)
                saleval = cols.get("sales_value", 0.0)
                cl = cols.get("closing_stock", 0.0)
                clval = cols.get("closing_stock_value", 0.0)

                # A genuine stock line always carries at least one QUANTITY column.
                # The footer "Totals:" line prints only value cells (no qty) and any
                # masthead artefact that leaks a lone value is dropped by this guard.
                if op == 0 and pur == 0 and sale == 0 and cl == 0:
                    continue

                records.append({
                    "product_name": name,
                    "pack": " ".join(pack_toks).strip(),
                    "opening_stock": op,
                    "purchase_stock": pur,
                    "sales_qty": sale,
                    "sales_value": saleval,
                    "closing_stock": cl,
                    "closing_stock_value": clval,
                })
    return records
