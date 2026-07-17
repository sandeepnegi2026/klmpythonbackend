"""Marg "Sales And Stock (Summary)" wide movement grid (MANDAL MEDICINE SUPPLY,
"klm n.xls"; report title "Sales And Stock (Summary)").

Single-row header, 15 columns:

    Product | Strength | OpStock | OpValue | In Stock | In Stock Value | Out Stock |
    Out Stock Value | Cl.Stock As On | Cl.Value | HSN/SAC | Cur.Stock | SGST |
    Cur.Stock Value | DumpStock

Column -> field mapping (bound by EXACT header text, positionally verified):

    Product          -> product_name
    Strength         -> pack
    OpStock          -> opening_stock          (qty)
    OpValue          -> opening_value
    In Stock         -> purchase_stock         (purchase / inward qty, +)
    In Stock Value   -> purchase_value
    Out Stock        -> sales_qty              (sales / outward qty, -)
    Out Stock Value  -> sales_value
    Cl.Stock As On   -> closing_stock          (qty)
    Cl.Value         -> closing_stock_value
    HSN/SAC          -> hsn_code
    SGST             -> gst_rate

Cur.Stock / Cur.Stock Value / DumpStock are the physical-on-hand and dump-adjusted
figures (Cur.Stock differs from Cl.Stock As On only when DumpStock is nonzero); they
are NOT part of the movement identity and are deliberately left unmapped so the
reconcile keys off the reported Cl.Stock As On.

Reconcile:  opening + purchase - sales = closing  holds on 146/146 source rows
(e.g. CANROLFIN CREAM 12 + 0 - 1 = 11 = Cl.Stock; CETALORE M SYP 0 + 30 - 20 = 10;
COSMOQ SHAMPOO 8 + 5 - 11 = 2). qty and value are read from SEPARATE columns; no
quantity is ever derived from a value column.

Why a dedicated parser: the generic `tabular` header matcher mis-binds this book --
it lets the "Cl.Stock As On" / "Cur.Stock" columns leak into purchase_stock (e.g.
CANROLFIN reads purchase_stock 11 instead of 0), so the stock identity fails on 92%
of rows (SANITY_FAILED) even though the SOURCE numbers reconcile exactly.

Distinct from r15_klm_name_to_display_stock_xls (whose leading columns are
"NameToDisplay | Marketing Group | OpStock(Unit1) | OpValue | ..." with a Unit1/Unit2
split and no "Product | Strength" head) and from klm_dstk_stock / central_stock_and_sales
(no "Product Strength OpStock OpValue In Stock In Stock Value Out Stock Out Stock Value"
run). Also carries the Marg report title "Sales And Stock (Summary)".

Gate token (compact, contiguous header run unique to this export):
    "productstrengthopstockopvalueinstockinstockvalueoutstockoutstockvalue"
"""
from extractors.stock_xlsx.parse_common import cell_text, is_subtotal, to_number

GATE_TOKEN = "productstrengthopstockopvalueinstockinstockvalueoutstockoutstockvalue"

# product-cell prefixes that mark a footer/section band, never a real medicine
_STOP_PRODUCT_PREFIXES = (
    "total", "grand total", "opening", "purchase", "sales", "closing",
    "company", "division", "manufacturer", "value", "amount", "page",
    "product", "sales and stock",
)

# exact header text -> field
_HEADER_MAP = {
    "product": "product_name",
    "strength": "pack",
    "opstock": "opening_stock",
    "opvalue": "opening_value",
    "in stock": "purchase_stock",
    "in stock value": "purchase_value",
    "out stock": "sales_qty",
    "out stock value": "sales_value",
    "cl.stock as on": "closing_stock",
    "cl.value": "closing_stock_value",
    "hsn/sac": "hsn_code",
    "sgst": "gst_rate",
}

_NUM_FIELDS = (
    "opening_stock", "opening_value", "purchase_stock", "purchase_value",
    "sales_qty", "sales_value", "closing_stock", "closing_stock_value",
    "gst_rate",
)

_TEXT_FIELDS = ("product_name", "pack", "hsn_code")


def _norm(cell):
    return cell_text(cell).strip().lower()


def _find_header(rows):
    """Return the index of the Product..DumpStock header row, or None."""
    for idx in range(min(len(rows), 30)):
        cells = [_norm(c) for c in rows[idx]]
        if cells[:2] == ["product", "strength"] and "opstock" in cells:
            return idx
    return None


def detect(rows):
    flat = " ".join(
        " ".join(cell_text(c) for c in row) for row in rows[:30]
    ).lower().replace(" ", "")
    return GATE_TOKEN in flat


def parse_marg_sales_stock_summary_opstock_instock_outstock_xls(rows):
    hdr = _find_header(rows)
    if hdr is None:
        return [], {}

    header_cells = [_norm(c) for c in rows[hdr]]
    col = {}
    for i, h in enumerate(header_cells):
        field = _HEADER_MAP.get(h)
        if field is not None and field not in col:
            col[field] = i

    # require the core identity columns to be present
    for req in ("product_name", "opening_stock", "purchase_stock", "sales_qty",
                "closing_stock"):
        if req not in col:
            return [], {}

    def num(raw_row, key):
        i = col.get(key)
        if i is None or i >= len(raw_row):
            return 0.0
        return to_number(raw_row[i]) or 0.0

    def txt(raw_row, key):
        i = col.get(key)
        if i is None or i >= len(raw_row):
            return ""
        return cell_text(raw_row[i]).strip()

    records = []
    for raw_row in rows[hdr + 1:]:
        if not any(cell_text(c) for c in raw_row):
            continue
        product = txt(raw_row, "product_name")
        if not product:
            continue
        pl = product.lower()
        if is_subtotal(product) or pl.startswith(_STOP_PRODUCT_PREFIXES):
            continue
        # skip a numeric-only "product" (footer total that leaked into the column)
        if pl.replace(".", "", 1).replace(",", "").isdigit():
            continue

        rec = {}
        for f in _TEXT_FIELDS:
            if f in col:
                rec[f] = txt(raw_row, f)
        for f in _NUM_FIELDS:
            if f in col:
                rec[f] = num(raw_row, f)
        records.append(rec)

    detected = {
        "Product": "product_name",
        "Strength": "pack",
        "OpStock": "opening_stock",
        "OpValue": "opening_value",
        "In Stock": "purchase_stock",
        "In Stock Value": "purchase_value",
        "Out Stock": "sales_qty",
        "Out Stock Value": "sales_value",
        "Cl.Stock As On": "closing_stock",
        "Cl.Value": "closing_stock_value",
        "HSN/SAC": "hsn_code",
        "SGST": "gst_rate",
    }
    return records, detected
