"""KLM / VISION "Product wise sale list (Combined)" party-wise sales register.

A very wide (26-column) banded register whose PDF prints EACH CELL'S TEXT STACKED
VERTICALLY at a stable x — one character (or short chunk) per baseline, top to
bottom — so the flat text layer is unreadable garble (the column HEADER itself is
stacked). We therefore rebuild the report POSITIONALLY:

  * Every column has a fixed x0 anchor (read off the header / data):
      Branch@58  Date@74  BillNo@94  Product@124  HSN@152  Pack@166  Batch@179
      Ex.Dt@198  Qty@217  Free@237  Repl@254  Rate@272  Value@291 ...
      Customer@483  Place@511  PIN@529
  * The report is banded:  a Customer NAME band (only the Product column carries
    text) -> one or more product SALE lines -> a "Customer Total" subtotal band,
    ending in a "Grand Total" band. On every sale line the Customer column (x=483)
    ALSO repeats the party name, so we read party per line (no band carry needed).
  * Each sale line is anchored by its Date cell (x~74): the date "DD/MM/YY" stacks
    as 10-px chunks, so the first top of that contiguous run is the record's top.
    (The Branch code is NOT a reliable anchor — it varies HO / M / WE...) We clip
    each record's vertical band at the next date-anchor (or Total marker), then
    de-stack every column by concatenating its words top-to-bottom within the band.

Value is the line amount (Qty*Rate); Free is a real qty column (free/replacement
lines legitimately carry Qty=0). "Customer Total" / "Grand Total" bands have no
Date cell, and their tops are used only to clip the preceding line's band.
"""
import io
import re

import pdfplumber

# (name, x0-anchor). Kept in x order; a word is assigned to the nearest anchor
# within _X_TOL. Anchors are ~16-20 px apart so single-glyph digits bucket cleanly.
_ANCHORS = [
    ("branch", 58),
    ("date", 74),
    ("bill", 94),
    ("product", 124),
    ("hsn", 152),
    ("pack", 166),
    ("batch", 179),
    ("exdt", 198),
    ("qty", 217),
    ("free", 237),
    ("repl", 254),
    ("rate", 272),
    ("value", 291),
    ("srate", 311),
    ("svalue", 330),
    ("pdis", 348),
    ("bdis", 365),
    ("scheme", 383),
    ("gst", 398),
    ("trrate", 411),
    ("cgst", 429),
    ("sgst", 448),
    ("igst", 467),
    ("customer", 483),
    ("place", 511),
    ("pin", 529),
]
_X_TOL = 8.0

_NUM = re.compile(r"-?\d[\d,]*\.?\d*$")
_D2 = re.compile(r"^\d{2}$")  # 2-digit day chunk that opens each Date cell

HEADERS = ["Party Name", "Place", "Product Name", "Pack", "Qty", "Free", "Rate", "Value"]


def _col_of(x0):
    best, bd = None, 1e9
    for name, ax in _ANCHORS:
        d = abs(x0 - ax)
        if d < bd:
            bd, best = d, name
    return best if bd <= _X_TOL else None


def _to_f(t):
    t = t.replace(",", "")
    try:
        return float(t)
    except ValueError:
        return 0.0


def _clean_name(s):
    # collapse the de-stacked glyph run into a spaced-out best-effort name; the
    # source prints uppercase words with no spaces, so leave as-is but trim.
    return re.sub(r"\s+", " ", s).strip()


def parse_product_wise_sale_combined(text, file_bytes=None):
    if not file_bytes:
        return HEADERS, []

    rows = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            words = page.extract_words(x_tolerance=1.5, y_tolerance=2)
            if not words:
                continue

            # A sale line is anchored by its Date cell. The Date column (x~74)
            # stacks the date "DD/MM/YY" as chunks 10 px apart (DD, /M, M/, YY),
            # so a whole cell is a contiguous run of date-column tops; the run's
            # FIRST top is the record's top. (The Branch code is NOT reliable — it
            # varies HO / M / WE... — so we key on the date column instead.)
            date_tops = sorted(
                round(w["top"], 1) for w in words if abs(w["x0"] - 74) < 6
            )
            sale_tops = []
            prev = None
            for t in date_tops:
                if prev is None or t - prev > 12:
                    sale_tops.append(t)
                prev = t
            # "Customer Total" / "Grand Total" bands print in the Product column and
            # start with a first chunk "Cus" (CustomerTotal) or "Gra" (GrandTotal).
            # Their tops END the preceding sale segment so their totals never fold
            # into the last line.
            total_tops = sorted(
                round(w["top"], 1)
                for w in words
                if abs(w["x0"] - 124) < 6 and w["text"] in ("Cus", "Gra")
            )
            if not sale_tops:
                continue

            # Segment boundaries = every sale start + every total marker + a large
            # sentinel; each SALE segment is clipped at the next boundary above it,
            # so its de-stacked cells contain only that line's own text.
            boundaries = sorted(set(sale_tops) | set(total_tops) | {1e9})

            for st in sale_tops:
                hi = min(b for b in boundaries if b > st + 1)
                # tops are rounded to .1; clip with a 0.5 margin so a boundary row
                # (whose raw top ~= hi-0.01) is never pulled into the segment.
                band = [w for w in words if st - 1 <= w["top"] < hi - 0.5]
                cols = {}
                for w in band:
                    c = _col_of(w["x0"])
                    if c is None:
                        continue
                    cols.setdefault(c, []).append((w["top"], w["text"]))

                def joined(name):
                    return "".join(
                        t for _, t in sorted(cols.get(name, []), key=lambda p: p[0])
                    ).strip()

                product = _clean_name(joined("product"))
                customer = _clean_name(joined("customer"))
                place = _clean_name(joined("place"))
                pack = joined("pack")
                qty_s = joined("qty")
                free_s = joined("free")
                rate_s = joined("rate")
                value_s = joined("value")

                # A real sale line has a numeric qty and a numeric value.
                if not product or not customer:
                    continue
                low_prod = product.lower().replace(" ", "")
                if "customertotal" in low_prod or "grandtotal" in low_prod:
                    continue
                if not (_NUM.match(qty_s) and _NUM.match(value_s)):
                    continue

                rows.append(
                    [
                        customer,
                        place,
                        product,
                        pack,
                        _to_f(qty_s),
                        _to_f(free_s) if _NUM.match(free_s) else 0.0,
                        _to_f(rate_s) if _NUM.match(rate_s) else 0.0,
                        _to_f(value_s),
                    ]
                )
    return HEADERS, rows
