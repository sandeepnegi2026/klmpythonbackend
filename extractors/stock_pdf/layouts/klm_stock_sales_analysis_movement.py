"""KLM 'STOCK AND SALES ANALYSIS' — division-banded movement statement (no P.Code).

Vendor:  SANTOSH ENTERPRISES (KLM company), one PDF, sections banded by a bare
         division line (KLM / COSMO / COSMOCOR / PEDIA / PHARMA ... a single all-caps
         token line with NO trailing numbers).
Format:  flat text PDF (n_rects ~= 0).  Header line, printed once per page:

    PRODUCT  PACK  OPENING  PURCHASE  FREE  P.RETURN  FREE  SALE  FREE  S.RETURN  FREE  OTHERS  CLOSING

    11 numeric stat columns per product row (every zero cell prints '-'):
        [0]  OPENING    -> opening_stock
        [1]  PURCHASE   -> purchase_stock          (already net of purchase-return)
        [2]  FREE       -> purchase_free           (purchase free goods, INFLOW +)
        [3]  P.RETURN   -> purchase_return          (OUTFLOW -)
        [4]  FREE       -> purchase-return free     (folded into purchase_return, -)
        [5]  SALE       -> sales_qty                (OUTFLOW -)
        [6]  FREE       -> sales_free               (sale free goods, OUTFLOW -)
        [7]  S.RETURN   -> sales_return             (INFLOW +)
        [8]  FREE       -> sales-return free        (folded into sales_return, +)
        [9]  OTHERS     -> SIGNED adjustment, folded into purchase_return so it
                          SUBTRACTS from closing (same convention as klm_sale_stock
                          StkAdj / klm_stock_sales_analysis_pcode Adj).
        [10] CLOSING    -> closing_stock

Row shape:  <PRODUCT NAME ...> <PACK ...> <11 stat tokens>.  A trailing pack-size
    number (TAB 10, -625, 100) may sit just before the stat block, giving 12/13
    trailing numbers; the stat block is ALWAYS the last 11, so we count from the
    RIGHT (identical to klm_stock_sales_analysis_pcode) and leave the pack digit
    with the name.  The PACK is recovered by the shared peeler (informational).

Reconcile (vendor identity == triage sanity):
    CLOSING = OPENING + PURCHASE + PURCHASE_FREE - P.RETURN(+free) - SALE - SALE_FREE
              + S.RETURN(+free) - OTHERS
    i.e. closing = opening + purchase_stock + purchase_free + sales_return
                   - sales_qty - sales_free - purchase_return.

    The report footer prints VALUE totals (rupees) only, not per-row values, so
    reconcile is per-row QTY identity (this is a qty-only body).
"""

import re

from extractors.stock_pdf.parse_common import _skip_line, _split_product_pack

# a stat token: integer / decimal / signed, or a bare '-' zero placeholder.
_STAT = re.compile(r"^-?\d+(?:\.\d+)?$|^-$")

_N_STATS = 11  # OPENING PURCHASE FREE P.RETURN FREE SALE FREE S.RETURN FREE OTHERS CLOSING


def _v(tok):
    return 0.0 if tok == "-" else float(tok.replace(",", ""))


def parse_klm_stock_sales_analysis_movement(text):
    records = []
    division = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue

        parts = line.split()
        # bare division band: a SINGLE all-caps alpha token line (e.g. COSMO /
        # COSMOCOR / COSMOQ / DERMA / DERMACOR / PEDIA / PHARMA). Track it, don't
        # emit a row. Single-token keeps the 2-word vendor/address header lines out.
        if len(parts) == 1 and re.fullmatch(r"[A-Z][A-Z]+", line):
            division = line
            continue

        if _skip_line(line):
            continue
        if len(parts) < _N_STATS + 1:  # at least a name + 11 stats
            continue

        tail = parts[-_N_STATS:]
        if not all(_STAT.match(t) for t in tail):
            continue

        vals = [_v(t) for t in tail]
        (opening, purchase, pur_free, p_ret, p_ret_free, sale, sale_free,
         s_ret, s_ret_free, others, closing) = vals

        # Everything before the stat block is 'NAME PACK'.
        middle = " ".join(parts[:-_N_STATS]).strip()
        if not middle or not re.search(r"[A-Za-z]", middle):
            continue
        name, pack = _split_product_pack(middle)
        name = re.sub(r"\s+", " ", name).strip()
        if not name or len(name) < 2:
            continue

        rec = {
            "product_name": name,
            "pack": pack,
            "division": division,
            "opening_stock": opening,
            "purchase_stock": purchase,
            "purchase_free": pur_free,
            # P.RETURN + its FREE + OTHERS all subtract from closing.
            "purchase_return": p_ret + p_ret_free + others,
            "sales_qty": sale,
            "sales_free": sale_free,
            # S.RETURN + its FREE add back to closing.
            "sales_return": s_ret + s_ret_free,
            "closing_stock": closing,
        }
        records.append(rec)
    return records
