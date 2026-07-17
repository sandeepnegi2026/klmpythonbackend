"""KLM COSMOCOR "STOCK & SALES STATEMENT" .xlsx — one division per sheet.

SHIVA KRUPA PHARMACEUTICAL DISTRIBUTORS. Multi-sheet workbook (COSMOCOR / COSMO /
COSMO Q / DERMA / DERMACOR / PEDIA); every sheet carries a 5-row title/address/period
band, then this 12-column split header (each label is a two-line cell):

    PRODUCT DESCRIPTION | OPENING STOCK | PURCHASE QUANTITY | SALE RETURN QUANTITY |
    REPLACE+OTHERS | TOTAL RECEIVE | SALE QUANTITY | P/R QUANTITY | REPLACE+OTHERS |
    CLOSING STOCK | RATE | LAST MONTH SALE

There are TWO "REPLACE+OTHERS" columns (one on the receive side, one on the sale side)
and a mid-row "TOTAL RECEIVE" subtotal, so the generic `tabular` reader mis-maps: it
drops the SALE QUANTITY column and every row that actually sold fails the sanity
equation (~54% RED). Decoded by 100% row reconciliation across all 6 sheets:

    CLOSING = OPENING + PURCHASE + SALE RETURN + REPLACE(recv)
                      - SALE - P/R - REPLACE(sale)

canonical mapping:

    OPENING STOCK          -> opening_stock
    PURCHASE QUANTITY      -> purchase_stock
    SALE RETURN QUANTITY   -> sales_return    (goods returned in, inflow)
    REPLACE+OTHERS (recv)  -> purchase_free   (replacements received, inflow)
    TOTAL RECEIVE          -> (skip: derived opening+purchase+sret+replace subtotal)
    SALE QUANTITY          -> sales_qty        (outflow)
    P/R QUANTITY           -> purchase_return  (goods returned to supplier, outflow)
    REPLACE+OTHERS (sale)  -> sales_free        (replacements issued, outflow)
    CLOSING STOCK          -> closing_stock
    RATE                   -> rate
    LAST MONTH SALE        -> (skip: informational prior-month qty)

which is exactly opening + purchase + purchase_free - purchase_return - sales_qty
- sales_free + sales_return = closing. The trailing "TOTAL VALUE" footer row (rupee
totals, not quantities) is skipped.

Gate token (compact, lowercased column-header run unique to this family):
    productdescriptionopeningstockpurchasequantitysalereturnquantity  +  totalreceive
"""
from extractors.stock_xlsx.parse_common import cell_text, to_number

_SKIP_PREFIXES = (
    "total", "grand", "product description", "opening", "closing", "purchase",
    "sale ", "sale\n",
)


def _compact(cell):
    return cell_text(cell).lower().replace(" ", "").replace("\n", "").replace(".", "")


def _find_header(rows):
    """Header row = the one whose compact cells run PRODUCT DESCRIPTION | OPENING STOCK |
    PURCHASE QUANTITY | SALE RETURN QUANTITY | REPLACE+OTHERS | TOTAL RECEIVE ..."""
    for idx, row in enumerate(rows[:20]):
        toks = [_compact(c) for c in row]
        if (len(toks) >= 10
                and toks[0] == "productdescription"
                and toks[1] == "openingstock"
                and toks[2] == "purchasequantity"
                and toks[3] == "salereturnquantity"
                and "totalreceive" in toks):
            return idx
    return None


def detect(rows):
    return _find_header(rows) is not None


# Fixed positional roles for this 12-column layout (indices are stable across sheets).
_ROLES = {
    0: "product_name",
    1: "opening_stock",
    2: "purchase_stock",
    3: "sales_return",     # SALE RETURN QUANTITY (inflow)
    4: "purchase_free",    # REPLACE+OTHERS receive side (inflow)
    # 5: TOTAL RECEIVE  -> derived subtotal, skip
    6: "sales_qty",        # SALE QUANTITY (outflow)
    7: "purchase_return",  # P/R QUANTITY (outflow)
    8: "sales_free",       # REPLACE+OTHERS sale side (outflow)
    9: "closing_stock",
    10: "rate",
    # 11: LAST MONTH SALE -> informational, skip
}

_NUMERIC = (
    "opening_stock", "purchase_stock", "sales_return", "purchase_free",
    "sales_qty", "purchase_return", "sales_free",
)


def parse_klm_ss_stmt_prod_desc(rows):
    header_idx = _find_header(rows)
    if header_idx is None:
        return [], {}

    records = []
    for raw in rows[header_idx + 1:]:
        cells = [cell_text(c) for c in raw]
        if not cells:
            continue
        product = cells[0].strip() if cells else ""
        low = product.lower()
        if not product or low.startswith(_SKIP_PREFIXES):
            continue
        # A merged section/footer band: one text repeated across the row.
        non_empty = [c for c in cells if c.strip()]
        if len(non_empty) > 1 and len(set(non_empty)) == 1:
            continue
        # A single-cell text row (e.g. the "MARG ERP NANO ... Call ..." advertising
        # footer): product text present but every quantity/rate column blank.
        if len(non_empty) <= 1:
            continue

        acc = {k: 0.0 for k in _NUMERIC}
        closing = None
        rate = None
        skip = False
        for idx, role in _ROLES.items():
            if idx >= len(cells):
                continue
            if role == "product_name":
                continue
            v = to_number(cells[idx])
            if role == "closing_stock":
                if v is None:
                    skip = True
                    break
                closing = v
                continue
            if role == "rate":
                rate = v
                continue
            if v is None:
                skip = True
                break
            acc[role] += v
        if skip or closing is None:
            continue

        record = {"product_name": product}
        for key, val in acc.items():
            record[key] = str(int(val)) if val == int(val) else str(val)
        record["closing_stock"] = str(int(closing)) if closing == int(closing) else str(closing)
        if rate is not None:
            record["rate"] = rate
        records.append(record)

    detected = {
        "PRODUCT DESCRIPTION": "product_name",
        "OPENING STOCK": "opening_stock",
        "PURCHASE QUANTITY": "purchase_stock",
        "SALE RETURN QUANTITY": "sales_return",
        "REPLACE+OTHERS(recv)": "purchase_free",
        "SALE QUANTITY": "sales_qty",
        "P/R QUANTITY": "purchase_return",
        "REPLACE+OTHERS(sale)": "sales_free",
        "CLOSING STOCK": "closing_stock",
        "RATE": "rate",
    }
    return records, detected
