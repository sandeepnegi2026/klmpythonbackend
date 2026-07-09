"""MediVision Platinum "Stock and Sales" report (SIND DISTRIBUTORS).

Header (y~160):
    Product name | Unit | Op | Purc | Scm | Purc val | Sale | Scm | Sa val | Cl qty | Cl val

This is an Adobe "Adobe-UTF-8" collection PDF: pdfplumber / pdfminer cannot map
its embedded glyphs (they return almost nothing and the file is misread as
scanned/empty), so pdf_io falls back to PyMuPDF for the `text` layer. We read the
same PDF with PyMuPDF here and bucket each word into its column by x0.

The numeric columns are RIGHT-ALIGNED and interior cells print BLANK for
no-movement products, so the flat-text token index does not identify the column;
positional (x0-band) bucketing is required. Column bands by word x0 (read off the
printed header + verified against the data rows):

    product name   : x0 < 150     (strip leading '.'/'..' discontinued-item dots)
    unit / pack     : 150 <= x0 < 205
    opening_stock   : 205 <= x0 < 248   (Op)
    purchase_stock  : 248 <= x0 < 290   (Purc)
    purchase_free   : 290 <= x0 < 322   (Scm)
    purchase_value  : 322 <= x0 < 365   (Purc val)
    sales_qty       : 365 <= x0 < 408   (Sale)
    sales_free      : 408 <= x0 < 448   (Scm)
    sales_value     : 448 <= x0 < 490   (Sa val)
    closing_stock   : 490 <= x0 < 528   (Cl qty)
    closing_value   : 528 <= x0 < 566   (Cl val)

Per-row reconciliation:
    closing_stock = opening_stock + purchase_stock + purchase_free
                    - sales_qty - sales_free
(verified e.g. CETALORE 96+38+12-51-16=79; CUTIHEAL 103+120+0-97-18=108).

The companies band ("Companies: KLM LABORATORIES PVT-KLM PHARM, ...") lists the
divisions covered by the whole report (not per-row), so there is no per-row
division/company column to map; the report grand-totals reconcile exactly to the
printed footer (purc_val 697869 / sale_val 721418 / closing_value 1231966).

Skipped lines: the lone "MediVision" watermark, the repeated page header (vendor
name / address / Phone / Email / "Stock and Sales" / "Companies: ..." / date
range / "Page No. N" / the "Product name Unit Op Purc..." header), the footer
totals ("Totals:", "Tot sale value:", "Tot purc value:", "Generated at ..."), and
pure product-name rows carrying NO numeric columns (zero-stock discontinued items,
often dot-prefixed).
"""
import re

# (upper x0 bound, field name) — a numeric word at x0 < bound lands in this column.
_COL_BANDS = [
    (248.0, "opening_stock"),
    (290.0, "purchase_stock"),
    (322.0, "purchase_free"),
    (365.0, "purchase_value"),
    (408.0, "sales_qty"),
    (448.0, "sales_free"),
    (490.0, "sales_value"),
    (528.0, "closing_stock"),
    (99999.0, "closing_stock_value"),
]

_NAME_X_MAX = 150.0   # product-name tokens
_PACK_X_MAX = 205.0   # unit / pack tokens
_NUM_X_MIN = 205.0    # numeric columns begin at Op

_NUM_RE = re.compile(r"^-?\d[\d,]*\.?\d*$")

# lowered joined-name fragments that mark a header / footer / banner line to skip
_SKIP_NAME_SUBSTR = (
    "medivision", "sind distributors", "companies:", "stock and sales",
    "product name", "page no", "generated at", "totals",
)


def _is_num(t):
    t = t.replace(",", "")
    return bool(_NUM_RE.fullmatch(t)) and any(c.isdigit() for c in t)


def _to_f(t):
    try:
        return float(t.replace(",", ""))
    except ValueError:
        return 0.0


def _bucket(x0):
    for bound, name in _COL_BANDS:
        if x0 < bound:
            return name
    return "closing_stock_value"


def parse_medivision_stock_sales(text, file_bytes=None):
    if not file_bytes:
        return []
    import fitz  # PyMuPDF — pdfminer cannot read this Adobe-UTF-8 CID export

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
                    x0, t = w[0], w[4]
                    if _is_num(t) and x0 >= _NUM_X_MIN:
                        cols.setdefault(_bucket(x0), _to_f(t))
                    elif x0 < _NAME_X_MAX:
                        name_toks.append(t)
                    elif x0 < _PACK_X_MAX:
                        pack_toks.append(t)

                # skip pure product-name rows (no numeric columns): discontinued /
                # zero-stock items, often dot-prefixed
                if not cols:
                    continue

                name = " ".join(name_toks).strip()
                # strip leading discontinued-item dots ('.', '..', '...')
                name = name.lstrip(".").strip()
                low = name.lower()

                # header / footer / banner / totals lines
                if any(s in low for s in _SKIP_NAME_SUBSTR):
                    continue
                if low.startswith("tot ") and "value" in low:  # Tot sale/purc value:
                    continue
                # footer "Totals:" prints its numbers with NO product name in the
                # name band (the label 'Totals:' sits at x0~289, inside the numeric
                # zone), so a valueless-name numeric row is the grand-total line.
                if not name:
                    continue

                op = cols.get("opening_stock", 0.0)
                pur = cols.get("purchase_stock", 0.0)
                purf = cols.get("purchase_free", 0.0)
                purval = cols.get("purchase_value", 0.0)
                sale = cols.get("sales_qty", 0.0)
                salef = cols.get("sales_free", 0.0)
                saleval = cols.get("sales_value", 0.0)
                cl = cols.get("closing_stock", 0.0)
                clval = cols.get("closing_stock_value", 0.0)

                # A genuine stock line always carries at least one QUANTITY column
                # (opening / purchase / purchase_free / sales / sales_free /
                # closing). The repeated page-header address row leaks its postal
                # code ("-444601") into the sales_value band with NO quantities, so
                # gating on "any quantity present" drops it (and any other value-only
                # header artefact) without touching a single product row.
                if (op == 0 and pur == 0 and purf == 0
                        and sale == 0 and salef == 0 and cl == 0):
                    continue

                records.append({
                    "product_name": name,
                    "pack": " ".join(pack_toks).strip(),
                    "opening_stock": op,
                    "purchase_stock": pur,
                    "purchase_free": purf,
                    "purchase_value": purval,
                    "sales_qty": sale,
                    "sales_free": salef,
                    "sales_value": saleval,
                    "closing_stock": cl,
                    "closing_stock_value": clval,
                })
    return records
