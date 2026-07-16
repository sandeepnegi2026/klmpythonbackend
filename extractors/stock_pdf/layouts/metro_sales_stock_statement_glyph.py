"""METRO MEDICAL AGENCIES "Sales & Stock Statement For the Period" — glyph-interleaved.

METRO exports this KLM stockist statement with the item code woven, digit by digit,
between the product-name letters ("33B0L4E9M9G9U0ARD FACE SERUM" for "BLEMGUARD FACE
SERUM") and — worse — the last two columns are printed OVERLAPPING in the same x-space,
so the plain text layer glues the closing-balance quantity to the closing value
("...4 757.63" / "...14714.92" where Cl Bal is 4/17 and the value is 757.63/414.92).

    Header: Product Name | Pack | Op Bal | Pur | Total | Sales | Cl Bal | C

`stock_op_pur_total_sale_close` matches this header but parses the naive text layer, so
it keeps the interleaved code in the name AND swallows the closing value into Cl Bal
(closing 11404.14 instead of 14 + value 404.14) -> mass SANITY_FAILED. This parser goes
back to the PDF char stream and maps every column POSITIONALLY:

  * The interleaved item-code is a SEPARATE text run drawn (in draw order) after the
    clean name run, starting at a smaller x — a backward x-jump. We split runs on that
    jump and keep only the letter-bearing (name) run, discarding the pure-digit code
    (same de-scramble idea as the KLM/Pharmabyte siblings).
  * The five quantity columns (Op Bal / Pur / Total / Sales / Cl Bal) are printed one
    font size SMALLER than the trailing closing-value column "C"; grouping the numeric
    chars by font size cleanly separates the glued Cl Bal quantity from the closing value.
  * Quantities are then bucketed to their column by the header right-edge x-anchor.

Mapping: opening_stock = Op Bal, purchase_stock = Pur (Total = op+pur, ignored),
sales_qty = Sales, closing_stock = Cl Bal, closing_stock_value = C.
Reconciles: Cl Bal = Op Bal + Pur - Sales (verified across every data row of all three
sample pages, e.g. BLEMGUARD 27 + 0 - 10 = 17; COSMO Q CONDITIONER 49 + 40 - 40 = 49).
qty/value split is preserved — the value column is never used to derive a quantity.
"""
import io
import re

import pdfplumber

# Column header right-edges (values are right-aligned to these; stable across pages/files).
_COLS = [
    ("opening_stock", 296.0),
    ("purchase_stock", 371.0),
    ("total", 438.0),          # printed op+pur, intentionally ignored
    ("sales_qty", 507.0),
    ("closing_stock", 575.0),
]
_NAME_X = 185.0   # Pack column starts here
_PACK_X = 258.0   # first quantity (Op Bal) column starts here
_VAL_FS = 8.5     # the "C" closing-value column is printed larger than the quantities
_COL_TOL = 20.0
_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _rows_by_top(chars):
    rows = {}
    for c in chars:
        if not c["text"].strip():
            continue
        key = None
        for y in rows:
            if abs(y - c["top"]) < 3.0:
                key = y
                break
        rows.setdefault(key if key is not None else c["top"], []).append(c)
    return rows


def _text_with_gaps(chars):
    """Join x-sorted chars, inserting a space across a visible horizontal gap."""
    out, last_x1 = [], None
    for c in sorted(chars, key=lambda c: c["x0"]):
        if last_x1 is not None and c["x0"] - last_x1 > 1.6:
            out.append(" ")
        out.append(c["text"])
        last_x1 = c["x1"]
    return "".join(out).strip()


def _name_chars(name_chars_draw):
    """Drop the interleaved item-code run: it is drawn after the name as a separate run
    that starts back at a smaller x (a backward x-jump). Keep only letter-bearing runs."""
    runs, cur, last_x1 = [], [], -1.0
    for c in name_chars_draw:
        if c["x0"] < last_x1 - 3.0:
            if cur:
                runs.append(cur)
            cur = [c]
        else:
            cur.append(c)
        last_x1 = c["x1"]
    if cur:
        runs.append(cur)
    out = []
    for r in runs:
        if re.search(r"[A-Za-z]", "".join(ch["text"] for ch in r)):
            out.extend(r)
    return out


def parse_metro_sales_stock_statement_glyph(text, file_bytes=None):
    if not file_bytes:
        return []
    records = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            for _top, chars in sorted(_rows_by_top(page.chars).items()):
                chars_draw = list(chars)
                xs = sorted(chars, key=lambda c: c["x0"])

                num_chars = [c for c in xs if c["x0"] >= _PACK_X]
                val_chars = [c for c in num_chars if c.get("size", 0) >= _VAL_FS]
                qty_chars = [c for c in num_chars if c.get("size", 0) < _VAL_FS]
                # A real product line carries the larger-font closing-value column; the
                # title / date / company / Total / Purchase-details rows do not.
                if not val_chars:
                    continue

                name = _text_with_gaps(_name_chars([c for c in chars_draw if c["x0"] < _NAME_X]))
                pack = _text_with_gaps([c for c in xs if _NAME_X <= c["x0"] < _PACK_X])
                if not name or not re.search(r"[A-Za-z]{2}", name) or "/" in name:
                    continue

                col = {k: [] for k, _ in _COLS}
                for c in qty_chars:
                    best, bd = None, _COL_TOL
                    for k, ax in _COLS:
                        d = abs(c["x1"] - ax)
                        if d < bd:
                            best, bd = k, d
                    if best:
                        col[best].append(c)
                vals = {
                    k: "".join(ch["text"] for ch in sorted(v, key=lambda c: c["x0"]))
                    for k, v in col.items()
                }

                # every mapped quantity must be a clean number; this rejects the header
                # row ('Op Bal'/'Pur'/'Sales'/'Cl Bal') and any stray label token.
                have_qty = False
                for k in ("opening_stock", "purchase_stock", "sales_qty", "closing_stock"):
                    v = vals.get(k, "")
                    if v == "":
                        continue
                    have_qty = True
                    if not _NUM_RE.fullmatch(v):
                        have_qty = False
                        break
                if not have_qty:
                    continue
                if not vals.get("opening_stock") and not vals.get("closing_stock"):
                    continue

                clval = "".join(ch["text"] for ch in sorted(val_chars, key=lambda c: c["x0"]))
                rec = {
                    "product_name": name,
                    "pack": pack,
                    "opening_stock": vals.get("opening_stock", ""),
                    "purchase_stock": vals.get("purchase_stock", ""),
                    "sales_qty": vals.get("sales_qty", ""),
                    "closing_stock": vals.get("closing_stock", ""),
                }
                if _NUM_RE.fullmatch(clval or ""):
                    rec["closing_stock_value"] = clval
                records.append(rec)
    return records
