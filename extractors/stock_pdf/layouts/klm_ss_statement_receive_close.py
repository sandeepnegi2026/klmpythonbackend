"""KLM LABS (DERMA) 'STOCK & SALES STATEMENT' — two-page receive/close statement.

SHREE DURGESHWARI PHARMA DISTRIBUTORS (Marg/KLM ERP). The report is split across
two physically separate page blocks that must be JOINED by row index:

    PAGE 1 header:
        PRODUCT DESCRIPTION | OPENING STOCK | PURCHASE QUANTITY |
        SALE RETURN QUANTITY | REPLACE+ OTHERS | TOTAL RECEIVE
      -> each product row carries name + 5 receipt numbers
         [opening, purchase, sale_return, replace, TOTAL]
      TOTAL = OPENING + PURCHASE + SALE_RETURN + REPLACE (all IN).

    PAGE 2 header (SAME product order, NO names, values only):
        SALE QUANTITY | P/R QUANTITY | REPLACE+ OTHERS | CLOSING STOCK | RATE
      -> each row [sale, p_r, replace, closing, rate]

The two pages share the identical product order and row count, so page-2 row *i*
completes page-1 row *i*. This differs from the receipts-only ``marg_pds_replace``
sibling (which has NO sale/closing page and treats page-1 TOTAL as closing) — here
the REAL closing comes from page 2.

Per-product identity (verified, 0 mismatches):  closing = TOTAL - sale - p_r
and canonically  closing = opening + purchase - purchase_return - sales + sales_return.

Mapping:
    opening_stock       = p1[0]
    purchase_stock      = p1[1] + p1[3]      (purchase qty + REPLACE+ receive; both IN)
    sales_return        = p1[2]
    sales_qty           = p2[0]              (SALE QUANTITY)
    purchase_return     = p2[1]              (P/R quantity, goods returned OUT)
    closing_stock       = p2[3]              (real CLOSING STOCK)
    rate                = p2[4]
    closing_stock_value = closing_stock * rate
"""

import re

from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_numbers,
    _split_product_pack,
)

# Page-2 header marker: "SALE P/R REPLACE+ CLOSING RATE" (compact 'salep/rreplace+closing').
_P2_HEADER_RE = re.compile(r"sale\s+p/?r\s+replace\+?\s+closing", re.I)


def parse_klm_ss_statement_receive_close(text):
    lines = text.splitlines()

    # 1) Locate the page-2 header to split the two blocks. The header word run may
    #    span two physical lines ("SALE P/R REPLACE+ CLOSING RATE" / "QUANTITY ...");
    #    match on the first line that carries the SALE..CLOSING run.
    split_idx = None
    for i, ln in enumerate(lines):
        if _P2_HEADER_RE.search(ln.strip()):
            split_idx = i
            break

    p1_lines = lines if split_idx is None else lines[:split_idx]
    p2_lines = [] if split_idx is None else lines[split_idx + 1:]

    # 2) PAGE 1 — product rows with 5 numeric columns.
    page1 = []
    for line in p1_lines:
        s = line.strip()
        if _skip_line(s):
            continue
        prod, tail, exp = _split_product_numbers(s)
        if not prod:
            continue
        vals = _nums(tail)
        if len(vals) < 5:
            continue
        name, pack = _split_product_pack(prod)
        page1.append(
            {
                "name": name,
                "pack": pack,
                "opening": vals[0],
                "purchase": vals[1],
                "sale_return": vals[2],
                "replace": vals[3],
                "total": vals[4],
                "expiry": exp,
            }
        )

    # 3) PAGE 2 — pure-number rows (no names), 5 columns each, in the same order.
    #    Drop the two trailing grand-total lines (TOTAL QUANTITY / TOTAL VALUE) which
    #    also render as bare number rows; keep only as many rows as page-1 products.
    page2 = []
    for line in p2_lines:
        s = line.strip()
        if not s:
            continue
        toks = s.split()
        # a data / total row is entirely numeric (allow leading '-' and decimals)
        if not all(re.fullmatch(r"-?\d+(?:\.\d+)?", t) for t in toks):
            continue
        vals = _nums(toks)
        if len(vals) < 5:
            continue
        page2.append(vals[:5])

    # Keep only the per-product rows (first N == len(page1)); the remaining lines are
    # the TOTAL QUANTITY / TOTAL VALUE grand-total rows.
    n = len(page1)
    page2 = page2[:n]

    records = []
    for i, p in enumerate(page1):
        p2 = page2[i] if i < len(page2) else [0.0, 0.0, 0.0, 0.0, 0.0]
        sale, p_r, _rpl2, closing, rate = p2
        r = {
            "product_name": p["name"],
            "pack": p["pack"],
            "opening_stock": p["opening"],
            "purchase_stock": p["purchase"] + p["replace"],  # purchase + REPLACE+ (both IN)
            "purchase_return": p_r,
            "sales_qty": sale,
            "sales_return": p["sale_return"],
            "closing_stock": closing,
            "rate": rate,
            "closing_stock_value": round(closing * rate, 2),
        }
        if p["expiry"]:
            r["expiry"] = p["expiry"]
        records.append(r)
    return records
