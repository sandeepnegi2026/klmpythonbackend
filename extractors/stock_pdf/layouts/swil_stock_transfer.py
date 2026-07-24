"""BIDYA PHARMA 'Sales & Stock Statement' — SwilERP transfer-column export.

SwilERP sibling of swil_stock_lastpurc / medtraders_sales_stock_statement, but the
richest column set of the family: it breaks out TRANSFER-IN and TRANSFER-OUT stock
movements and carries a Qty+Value pair for every measure.

Header (two physical lines):
    PRODUCT NAME  PACKING  Op.Opening Bal  Receipt/Pur  Transin/Transfer In  Total
      Issue/Sales  TranOut/TRANSFER  Closing/Closing Bala  Dump  Near
    (units)        Qty. Value  Qty. Value  Qty. Value  Qty.  Qty. Value  Qty. Value
      Qty. Value   Stock  Expiry

Each data line ends in EXACTLY 15 numbers (right-aligned, blank interiors filled
with 0), in this fixed order:
    0 Op.Qty   1 Op.Value    2 Rec.Qty  3 Rec.Value   4 Trin.Qty  5 Trin.Value
    6 Total.Qty (= Op+Rec+Trin, printed cross-check)
    7 Iss.Qty  8 Iss.Value   9 TrOut.Qty 10 TrOut.Value  11 Cl.Qty  12 Cl.Value
    13 Dump.Stock  14 Near-Expiry
e.g. OFACITIX TABLET 1X10 TABS  12 1383.86 120 13179.00 0 0.00 132 102 12446.55
     0 0.00 30 3459.65 0 0  ->  Op 12, Rec 120, Trin 0, Total 132, Iss 102,
     TrOut 0, Cl 30, Dump 0.

MAPPING (Transin is a stock inflow -> purchase_free; TranOut a stock outflow ->
sales_free), so the canonical reconcile
    closing = opening + purchase + purchase_free - sales - sales_free
    = Op + Rec + Trin - Iss - TrOut
holds exactly (OFACITIX: 12 + 120 + 0 - 102 - 0 = 30). The Dump (near-expiry) and
Near-Expiry columns are unsaleable SUBSETS already contained in Closing (Cl 12,
Dump 6 -> the 6 are part of the 12), so folding them in would double-count and break
the reconcile — they are IGNORED, exactly as the swil_stock_lastpurc sibling ignores
its Dump column.

The two header lines end in non-numeric tokens (Dump/Near, Stock/Expiry) and the
TOTAL / GRAND TOTAL footers carry only eight rupee numbers, so none of them satisfy
the anchored 15-number row regex — no explicit skip list is needed (the company band
and division bands are caught by _skip_line as a belt-and-braces guard).
"""
import re

from extractors.stock_pdf.parse_common import _skip_line, _split_product_pack

_N = r"-?[\d,]*\d(?:\.\d+)?"  # integer or decimal, optional commas / leading sign
_ROW_RE = re.compile(r"^(?P<body>.+?)\s+(" + (_N + r"\s+") * 14 + _N + r")\s*$")
# Trailing pack cell: "1 X10TABS", "1x15gm", "1X125ML", "1 X 50ML", "1X10 TABS".
_PACK_RE = re.compile(r"\s*(\d+\s*[xX*]\s*\d*\s*[A-Za-z][\w.'/ ]*?)\s*$")


def _f(tok):
    try:
        return float(tok.replace(",", ""))
    except ValueError:
        return 0.0


def _split_name_pack(body):
    body = body.strip()
    m = _PACK_RE.search(body)
    if m and m.start() > 0:
        name = body[: m.start()].strip()
        pack = m.group(1).strip()
        if name:
            return name, pack
    name, pack = _split_product_pack(body)
    return (name or body), pack


def parse_swil_stock_transfer(text, file_bytes=None):
    records = []
    for raw in (text or "").splitlines():
        s = raw.strip()
        if _skip_line(s):
            continue
        m = _ROW_RE.match(s)
        if not m:
            continue
        v = [_f(t) for t in m.group(2).split()]
        if len(v) != 15:
            continue

        name, pack = _split_name_pack(m.group("body"))
        records.append({
            "product_name": name,
            "pack": pack,
            "opening_stock": v[0],
            "opening_value": v[1],
            "purchase_stock": v[2],
            "purchase_value": v[3],
            "purchase_free": v[4],      # Transfer-In qty (stock inflow)
            "purchase_return": 0.0,
            "sales_qty": v[7],
            "sales_value": v[8],
            "sales_free": v[9],         # Transfer-Out qty (stock outflow)
            "sales_return": 0.0,
            "closing_stock": v[11],
            "closing_stock_value": v[12],
            "total_stock": v[6],        # printed Op+Rec+Trin cross-check
        })
    return records
