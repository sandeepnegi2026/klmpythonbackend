"""RAOUSHAN PHARMA 'Sales & Stock Statement Company [Summary]' — SwilERP export.

A company/division-summary dialect of the SwilERP stock statement. Each row carries a
leading item CODE (the 'NO' column) and exactly SEVEN trailing numbers:

    NO  PRODUCT / COMPANY  OP QTY  IN QTY  OP+IN QTY  OUT QTY  OUT AMT  CL QTY  CL AMT
    ^code ^name            [0]     [1]     [2]        [3]      [4]      [5]     [6]

e.g. '2913 KLM KLIN AHA F/W 100ML 1.0 12.0 13 4.0 893.28 9.0 1808.91'
     -> code 2913, OP 1, IN 12, OP+IN 13, OUT 4, OUT-Amt 893.28, CL 9, CL-Amt 1808.91

MAPPING: opening <- OP, purchase <- IN, sales_qty <- OUT, sales_value <- OUT AMT,
closing <- CL, closing_stock_value <- CL AMT. OP+IN[2] is the printed opening+inflow
cross-check (kept as total_stock, not reconciled against). There are no free/return
columns, so the canonical reconcile is
    closing = opening + purchase - sales   (= OP + IN - OUT)
which holds on every row of all four RAOUSHAN divisions (DERMA/DERMACOR/PHARMA/KLM-05).

Rows are anchored on: a leading all-digit CODE + a tail of exactly seven numeric cells.
A product whose name ends in a BARE pack size (e.g. 'NEVLON AD MOIST LOTION 150 ...')
prints eight trailing numbers; taking the LAST seven as the stat block leaves that
'150' correctly inside the name. The division bands ('KLM DERMACOR [784]'), the two
header lines ('NO PRODUCT ...'), and the TOTAL / GRAND TOTAL footers (three numbers,
non-digit first token) never satisfy the anchor, so no explicit skip list is needed.
"""
import re

from extractors.stock_pdf.parse_common import _split_product_pack

_NUM = re.compile(r"^-?[\d,]*\d(?:\.\d+)?$")


def _is_num(tok):
    return bool(_NUM.match(tok))


def _f(tok):
    try:
        return float(tok.replace(",", ""))
    except ValueError:
        return 0.0


def parse_swil_stock_company_summary(text, file_bytes=None):
    records = []
    for raw in (text or "").splitlines():
        s = raw.strip()
        toks = s.split()
        if len(toks) < 9:                       # code + >=1 name token + 7 stats
            continue
        if not toks[0].isdigit():               # every data row starts with the NO code
            continue
        stats = toks[-7:]
        if not all(_is_num(t) for t in stats):
            continue
        name_toks = toks[1:-7]
        if not name_toks:
            continue

        v = [_f(t) for t in stats]
        op, inq, _opin, out, out_amt, cl, cl_amt = v
        name, pack = _split_product_pack(" ".join(name_toks))
        records.append({
            "product_name": name or " ".join(name_toks),
            "pack": pack,
            "opening_stock": op,
            "purchase_stock": inq,
            "purchase_free": 0.0,
            "purchase_return": 0.0,
            "sales_qty": out,
            "sales_value": out_amt,
            "sales_free": 0.0,
            "sales_return": 0.0,
            "closing_stock": cl,
            "closing_stock_value": cl_amt,
            "total_stock": _opin,   # printed OP+IN cross-check
        })
    return records
