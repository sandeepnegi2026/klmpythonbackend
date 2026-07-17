"""KLM "STOCK AND SALES STATEMENT" scheme+transfer movement grid (HMRS PHARMA CARE LLP /
ATLANTA AGEN., "STOCK_AND_SALES_STATEMENT_..._Sheetal.xlsx").

Single-row header, 11 columns:

    PCode | Product Name | Packing | OPSTK | PURC | PSCH | IN | SALE | SSCH | OUT | STOCK

    OPSTK -> opening_stock
    PURC  -> purchase_stock      (purchase inflow, +)
    PSCH  -> purchase_free       (purchase-scheme free goods received, +)
    IN    -> sales_return        (goods-received inflow adjustment, +)   [see note]
    SALE  -> sales_qty           (sales outflow, -)
    SSCH  -> sales_free          (free-on-sale outflow, -)
    OUT   -> purchase_return     (goods-out outflow adjustment, -)
    STOCK -> closing_stock

Why a dedicated parser: the closing column is the bare abbreviation "STOCK", which the
generic `tabular` header matcher does NOT bind to closing_stock (it stays unmapped), so
closing_stock reads 0 on EVERY row and the whole book fails the stock identity
(SANITY_FAILED on 99% of rows) even though the SOURCE numbers reconcile exactly. The
scheme columns PSCH/SSCH and the transfer columns IN/OUT are also unbound by the generic
matcher (short/ambiguous tokens). This is NOT the same as klm_dstk_stock (which requires
STOCKV+SALEV or STOCK+LZSTK — this file has neither) nor gs_stock_sales_wide27_xlsx
(which requires PURCV+SALEV+EXSTKV+parentmanufacturer — absent here).

IN / OUT sign choice: verified on the source numbers. The 6 rows with a nonzero IN all
satisfy  OPSTK + PURC + IN - SALE = STOCK  (e.g. SOFIKID ZN DROPS 16+21+2-3=36=STOCK;
NIOSALIC OINT 6+25+10-18=23=STOCK), so IN is an inflow (+) and OUT its outflow (-)
counterpart. Mapping IN->sales_return (+ slot) and OUT->purchase_return (- slot) makes
the canonical identity
    opening + purchase + purchase_free - purchase_return - sales_qty - sales_free + sales_return = closing
hold on 258/258 rows in this file. PSCH/SSCH/OUT are all zero in the sample but are bound
by their + / - roles so any future book with scheme/return goods still reconciles.

Gate token (compact, contiguous header run unique to this export): the movement run
"opstkpurcpschinsalesschoutstock". The klm_dstk_stock / gs_stock_sales_wide27 families do
not carry the PSCH/SSCH/IN/OUT columns between OPSTK and STOCK, so this run is disjoint.
"""
from extractors.stock_xlsx.parse_common import cell_text, is_subtotal, to_number

# product-cell prefixes that mark a footer/section band, never a real medicine
_STOP_PRODUCT_PREFIXES = (
    "total", "grand total", "opening", "purchase", "sales", "closing",
    "company", "division", "manufacturer", "value", "amount", "page",
    "pcode", "product name",
)

# the exact movement-column sequence, normalized (lower, spaces stripped)
_HEADER_SEQUENCE = ["pcode", "product name", "packing", "opstk", "purc",
                    "psch", "in", "sale", "ssch", "out", "stock"]


def _norm(cell):
    return cell_text(cell).strip().lower()


def _find_header(rows):
    """Return the index of the PCode..STOCK header row, or None."""
    for idx in range(min(len(rows), 30)):
        cells = [_norm(c) for c in rows[idx]]
        # match the leading movement run allowing trailing empty cells
        head = [c for c in cells if c]
        if head[: len(_HEADER_SEQUENCE)] == _HEADER_SEQUENCE:
            return idx
    return None


def detect(rows):
    flat = " ".join(
        " ".join(cell_text(c) for c in row) for row in rows[:30]
    ).lower().replace(" ", "")
    return (
        "opstkpurcpschinsalesschoutstock" in flat
        # the report title anchors it to this KLM stock-and-sales export family
        and "stockandsalesstatement" in flat
    )


def parse_klm_opstk_psch_in_ssch_out_stock_xls(rows):
    hdr = _find_header(rows)
    if hdr is None:
        return [], {}

    # bind columns by exact position within the header row (map by exact header text)
    header_cells = [_norm(c) for c in rows[hdr]]
    col = {}
    for i, h in enumerate(header_cells):
        if h == "product name":
            col["product_name"] = i
        elif h == "packing":
            col["pack"] = i
        elif h == "pcode":
            col["hsn_code"] = i
        elif h == "opstk":
            col["opening_stock"] = i
        elif h == "purc":
            col["purchase_stock"] = i
        elif h == "psch":
            col["purchase_free"] = i
        elif h == "in":
            col["sales_return"] = i        # inflow adjustment (+)
        elif h == "sale":
            col["sales_qty"] = i
        elif h == "ssch":
            col["sales_free"] = i
        elif h == "out":
            col["purchase_return"] = i      # outflow adjustment (-)
        elif h == "stock":
            col["closing_stock"] = i

    # require the core identity columns to be present
    for req in ("product_name", "opening_stock", "purchase_stock", "sales_qty",
                "closing_stock"):
        if req not in col:
            return [], {}

    _NUM_FIELDS = ("opening_stock", "purchase_stock", "purchase_free",
                   "sales_return", "sales_qty", "sales_free",
                   "purchase_return", "closing_stock")

    def num(raw_row, key):
        i = col.get(key)
        if i is None or i >= len(raw_row):
            return 0.0
        return to_number(raw_row[i]) or 0.0

    records = []
    for raw_row in rows[hdr + 1:]:
        if not any(cell_text(c) for c in raw_row):
            continue
        pi = col["product_name"]
        product = cell_text(raw_row[pi]) if pi < len(raw_row) else ""
        if not product:
            continue
        pl = product.strip().lower()
        if is_subtotal(product) or pl.startswith(_STOP_PRODUCT_PREFIXES):
            continue
        # skip a numeric-only "product" (footer total that leaked into the column)
        if pl.replace(".", "", 1).isdigit():
            continue

        rec = {
            "product_name": product,
            "pack": cell_text(raw_row[col["pack"]]) if "pack" in col and col["pack"] < len(raw_row) else "",
        }
        hi = col.get("hsn_code")
        if hi is not None and hi < len(raw_row):
            rec["hsn_code"] = cell_text(raw_row[hi])
        for f in _NUM_FIELDS:
            if f in col:
                rec[f] = num(raw_row, f)
        records.append(rec)

    detected = {
        "PCode": "hsn_code",
        "Product Name": "product_name",
        "Packing": "pack",
        "OPSTK": "opening_stock",
        "PURC": "purchase_stock",
        "PSCH": "purchase_free",
        "IN": "sales_return",
        "SALE": "sales_qty",
        "SSCH": "sales_free",
        "OUT": "purchase_return",
        "STOCK": "closing_stock",
    }
    return records, detected
