"""KLM / SmartPharma360 'Stock And Sales Report (new)' — Qoh statement that prints a
PAIRED qty+value column for EVERY stage (Opening, Purchase, Sales, Qoh) rather than the
7-column qty-only shape that ``stock_qoh`` (parse_stock_qoh) handles.

Header (ABHIRAM MEDICAL AGENCIES / SmartPharma360):

    Product Name Pack Opstk Opening…Purc.Tot Purc Value Sales…Sale Value Qoh Qoh Value Age

Nine trailing numeric columns per data row:

    Opstk  OpeningValue  Purc.Tot  PurcValue  Sales  SaleValue  Qoh  QohValue  Age

Column map (reconciles: opening + purchase - sales = closing):
    col0 = Opstk        -> opening_stock
    col1 = OpeningValue -> opening_value
    col2 = Purc.Tot     -> purchase_stock
    col3 = Purc Value   -> purchase_value
    col4 = Sales        -> sales_qty
    col5 = Sale Value   -> sales_value
    col6 = Qoh          -> closing_stock
    col7 = Qoh Value    -> closing_stock_value
    col8 = Age (days)   -> ignored

The plain ``stock_qoh`` parser only collects 7 numeric columns from the right and starts
its qty mapping at Purc.Tot, so it drops the Opstk/Opening-Value pair entirely and reads
value columns as qty (sales_qty := Sale Value). That produces a 100%-rows SANITY_FAILED.

GATE TOKEN (spaces-stripped, lowercased, contiguous header run unique to this format):
    "purc.totpurcvaluesales"

Watermark handling mirrors ``stock_qoh``: strip a single bleed glyph PER-TOKEN inside the
numeric run only, so a legit digit+letter pack suffix to the left survives.
"""

from extractors.stock_pdf.parse_common import (
    _clean_number_token,
    _is_num,
    _skip_line,
    _split_product_pack,
    _to_number,
)

# Opstk OpeningValue Purc.Tot PurcValue Sales SaleValue Qoh QohValue Age
_MAX_COLS = 9
_MIN_COLS = 9


def _split_paired_line(s, max_cols=_MAX_COLS):
    """Split one raw statement line into (product+pack text, [column floats]).

    Walk tokens from the RIGHT, cleaning each per-token watermark glyph and dropping
    lone watermark letters, collecting up to ``max_cols`` numeric columns. Everything
    left of the run is returned RAW (product words + pack). Returns (None, []) when the
    line is not a full 9-column data row.
    """
    toks = s.split()
    if len(toks) < 4:
        return None, []
    vals = []
    i = len(toks) - 1
    while i >= 0 and len(vals) < max_cols:
        t = toks[i]
        c = _clean_number_token(t)
        if _is_num(c):
            vals.insert(0, _to_number(c) or 0.0)
            i -= 1
            continue
        if (
            len(t) == 1
            and t.isalpha()
            and i > 0
            and _is_num(_clean_number_token(toks[i - 1]))
        ):
            i -= 1
            continue
        break
    if len(vals) < _MIN_COLS:
        return None, []
    return " ".join(toks[: i + 1]), vals


def parse_stock_qoh_paired_value(text):
    """Parse the paired-value SmartPharma360 Qoh 'Stock And Sales Report (new)'."""
    records = []
    for line in text.splitlines():
        s = line.strip()
        if _skip_line(s):
            continue
        prod, vals = _split_paired_line(s)
        if not prod:
            continue
        # keep only the last 9 numeric columns (guards against a stray leading number
        # that would push the window; a genuine bare-number pack stays in ``prod``).
        vals = vals[-_MAX_COLS:]
        name, pack = _split_product_pack(prod)
        records.append({
            "product_name": name,
            "pack": pack,
            "opening_stock": vals[0],
            "opening_value": vals[1],
            "purchase_stock": vals[2],
            "purchase_value": vals[3],
            "sales_qty": vals[4],
            "sales_value": vals[5],
            "closing_stock": vals[6],
            "closing_stock_value": vals[7],
            # vals[8] = Age (days), ignored
        })
    return records
