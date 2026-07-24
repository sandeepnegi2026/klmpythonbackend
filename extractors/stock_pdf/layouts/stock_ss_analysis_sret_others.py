"""SAI KRISHNA AGENCIES (KLM ERP) 'STOCK AND SALES ANALYSIS' movement statement.

Header (single physical line, reprints atop every page):
    PRODUCT PACK  OPENING  PURCHASE  S.RETURN  OTHERS  SUB TOTAL  SALE  P.RETURN  OTHERS  CLOSING

Nine numeric columns per data row; every zero cell prints an explicit '-', so the
trailing numeric run is EXACTLY 9 tokens (dashes included).  Column order:
    v0 OPENING     -> opening_stock
    v1 PURCHASE    -> purchase_stock
    v2 S.RETURN    -> sales_return   (customer returns, inflow: +sr)
    v3 OTHERS(in)  -> purchase_free  (inflow, +pf)
    v4 SUB TOTAL   -> total_stock    (cross-check = op+pur+sret+others_in)
    v5 SALE        -> sales_qty      (outflow, -sal)
    v6 P.RETURN    -> purchase_return(returned to supplier, outflow: -pr)
    v7 OTHERS(out) -> sales_free      (outflow, -sf)
    v8 CLOSING     -> closing_stock

RECONCILE (canonical postprocess identity):
    closing == opening + purchase + purchase_free - purchase_return
               - sales_qty - sales_free + sales_return
    i.e.  CLOSING == OPENING + PURCHASE + OTHERS(in) - P.RETURN
                     - SALE - OTHERS(out) + S.RETURN
Verified per-row on 'klm june 26.pdf' (SAI KRISHNA): every non-zero row reconciles.

The value TOTAL footer (six rupee sums) is dropped — it has no leading product text
and its tokens are the only comma/decimal grouped run, so the letter-name guard and
the fixed 9-token requirement both exclude it.
"""
import re

from extractors.stock_pdf.parse_common import _split_product_pack

# Header / banner / page-decoration lines to skip.
_HEADER_TOKENS = ("productpackopening", "stockandsalesanalysis", "companygroup")
_SKIP_PREFIX = ("cont....", "sai krishna", "d.no", "from :", "page:")

# A single numeric cell: signed int/decimal (thousands-safe) OR a bare dash.
_NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*$")


def _is_cell(tok):
    if tok == "-" or tok == "-----":
        return True
    t = tok.replace(",", "")
    return bool(_NUM_RE.fullmatch(t)) and any(c.isdigit() for c in t)


def _to_f(tok):
    if tok in ("-", "-----"):
        return 0.0
    try:
        return float(tok.replace(",", ""))
    except ValueError:
        return 0.0


def parse_stock_open_pur_sret_others_subtotal(text):
    records = []

    for raw in (text or "").splitlines():
        s = raw.strip()
        if not s:
            continue
        low = s.lower()

        compact = low.replace(" ", "")
        if any(tok in compact for tok in _HEADER_TOKENS):
            continue
        if any(low.startswith(p) for p in _SKIP_PREFIX):
            continue
        # Value TOTAL footer: "TOTAL: 529186.74 ..." -> no product text, drop.
        if low.startswith("total"):
            continue

        # Pop the trailing numeric run (dashes count as cells).
        toks = s.split()
        tail = []
        body = list(toks)
        while body and _is_cell(body[-1]):
            tail.insert(0, body.pop())

        # Exactly 9 movement columns; anything else is not a data row.
        if len(tail) != 9 or not body:
            continue

        name = " ".join(body).strip()
        if not re.search(r"[A-Za-z]", name):
            continue

        v = [_to_f(t) for t in tail]

        prod, pack = _split_product_pack(name)
        prod = re.sub(r"\s+", " ", prod).strip()
        if not prod or len(prod) < 3:
            continue

        rec = {
            "product_name": prod,
            "pack": pack,
            "opening_stock": v[0],
            "purchase_stock": v[1],
            "sales_return": v[2],    # S.RETURN (inflow)
            "purchase_free": v[3],   # OTHERS (inflow)
            "total_stock": v[4],     # SUB TOTAL (cross-check)
            "sales_qty": v[5],       # SALE (outflow)
            "purchase_return": v[6], # P.RETURN (outflow)
            "sales_free": v[7],      # OTHERS (outflow)
            "closing_stock": v[8],   # CLOSING
        }
        if pack and prod != name:
            rec["_prestrip_name"] = name
        records.append(rec)

    return records
