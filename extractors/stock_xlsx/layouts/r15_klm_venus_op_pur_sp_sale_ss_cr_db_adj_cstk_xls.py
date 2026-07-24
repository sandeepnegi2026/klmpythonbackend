"""KLM "Stock and Sales Report" abbreviated-header .XLS — VENUS PHARMA (Ahmedabad)
export "KLM Statment June_26.XLS", division-banded (one book, several divisions).

Sheet shape (title / address / period rows on top, then one wide grid banded by
division "KLM LABORETIRES-COSMOCOR" etc. in a band row whose col0 is EMPTY)::

    VENUS  PHARMA.
    37, CELLER, SHUBHLAXMI COMPLEX, ... NARANPURA Ph:...
    Stock and Sales report From --> 01-Jun-26 to 30-Jun-26
    Item Name | Pack | 2026-04-30 | 2026-05-31 | Op. | Pur | SP | Sale | SS |
              SVal | Cr. | Db. | Adj. | C Stk | C Val | Ord.        <- header
    MG0018                                                           <- group-code marker
    (col1) KLM LABORETIRES-COSMOCOR   (col11) XA0000                 <- division band (col0 empty)
    AMOCLAFIX 625 TAB | 1*10 | ... | 35 | ... | 10 | ... | 25 | 3291.25   <- data row
    ...

Single header row. Movement columns mapped by EXACT header text (positional fallback):

    Op.   -> opening_stock          (opening qty)
    Pur   -> purchase_stock         (purchase qty, inflow +)
    SP    -> purchase_free          (scheme-on-purchase / free-purchase qty, inflow +)
    Sale  -> sales_qty              (sale qty, outflow -)
    SS    -> sales_free             (scheme-on-sale / free-sale qty, outflow -)
    SVal  -> sales_value            (sales rupee value — value only, never a qty)
    Cr.   -> sales_return           (credit note qty, inflow +)
    Db.   -> purchase_return        (debit note qty, outflow -)
    Adj.  -> signed adjustment folded into sales_return (+) / sales_free (-)
    C Stk -> closing_stock          (closing qty)
    C Val -> closing_stock_value    (closing rupee value)

The two bare date columns ("2026-04-30", "2026-05-31") are PRIOR month-end stock
history (informational) and are deliberately dropped. "Ord." (pending order) is dropped.

Reconciles EXACTLY on all 266 product rows of this book:
    closing = opening + purchase + purchase_free - purchase_return
              - sales_qty - sales_free + sales_return   (+/- Adj.)
e.g. EZACNE SACHET 5GM: 1198 == 967 + 1800 + 0 - 0 - 1435 - 281 + 150 (Cr) - 3 (Adj)
     KLCEPO 200 TAB:      29 ==  11 +   21 + 19 - 0 -  20 -   2 +   0

Why a dedicated parser rather than the generic `tabular` matcher:
  * The two bare month-end date columns and the informational "Ord." column fuzz-collide
    with the movement synonyms, and the abbreviated "SP"/"SS"/"Cr."/"Db."/"Adj." columns
    have no clean synonym home, so the generic index mapper mis-routes the movement columns
    and ~77% of rows fail the sanity equation.
  * Distinct from the sibling `klm_venus_opstk_crqty` VENUS export (KLM MAY.XLSX): that one
    puts the product name in col6, bands the division in col3 on EVERY data row, and its
    header uses OpStk / P.Qty / P.Sch / S.Qty / S.Sch / ClStk — none of the abbreviated
    "Op.  Pur  SP  Sale  SS  SVal  Cr.  Db.  Adj.  C Stk  C Val" tokens this book carries.

NEVER derives a quantity from a value column (SVal / C Val stay value-only).

Gate token (spaces stripped, lowercased contiguous header run, unique to this export):
    "op.purspsalesssval" AND "cr.db.adj.cstkcval"
"""
from extractors.stock_xlsx.parse_common import cell_text, is_subtotal, to_number


def _flat_row(row):
    return " ".join(cell_text(c) for c in row).lower().replace(" ", "")


def detect(rows):
    flat = " ".join(_flat_row(r) for r in rows[:12])
    return "op.purspsalesssval" in flat and "cr.db.adj.cstkcval" in flat


def _find_header(rows):
    for idx, row in enumerate(rows[:20]):
        flat = _flat_row(row)
        if "op.purspsalesssval" in flat and "cr.db.adj.cstkcval" in flat:
            return idx
    return None


# Exact header text (spaces stripped, lowercased) -> canonical column key.
_HDR = {
    "itemname": "product",
    "pack": "pack",
    "op.": "opstk",
    "pur": "pur",
    "sp": "sp",
    "sale": "sale",
    "ss": "ss",
    "sval": "sval",
    "cr.": "cr",
    "db.": "db",
    "adj.": "adj",
    "cstk": "cstk",
    "cval": "cval",
}


def _build_colmap(header_row):
    col = {}
    for i, cell in enumerate(header_row):
        key = cell_text(cell).lower().replace(" ", "")
        mapped = _HDR.get(key)
        if mapped and mapped not in col:
            col[mapped] = i
    return col


def parse_klm_venus_op_pur_sp_sale_ss_cr_db_adj_cstk_xls(rows):
    header_idx = _find_header(rows)
    if header_idx is None:
        return [], {}

    col = _build_colmap(rows[header_idx])
    for req in ("product", "opstk", "pur", "sale", "cstk"):
        if req not in col:
            return [], {}

    def num(raw_row, key):
        idx = col.get(key)
        if idx is None or idx >= len(raw_row):
            return 0.0
        return to_number(raw_row[idx]) or 0.0

    records = []
    for raw_row in rows[header_idx + 1:]:
        product = cell_text(raw_row[col["product"]]) if col["product"] < len(raw_row) else ""
        if not product or is_subtotal(product) or product in {".", "0"}:
            continue
        # Group-code marker rows (e.g. "MG0018") carry a short uppercase alnum code with
        # no spaces and no movement numbers — skip. Real products have letters+spaces.
        if " " not in product and product.replace("-", "").isalnum() and any(
            ch.isdigit() for ch in product
        ) and product == product.upper() and len(product) <= 8:
            continue

        opstk = num(raw_row, "opstk")
        pur = num(raw_row, "pur")
        sp = num(raw_row, "sp")
        sale = num(raw_row, "sale")
        ss = num(raw_row, "ss")
        cr = num(raw_row, "cr")
        db = num(raw_row, "db")
        cstk = num(raw_row, "cstk")

        # Skip empty rows (no movement at all).
        if not any([opstk, pur, sp, sale, ss, cr, db, cstk]):
            continue

        rec = {
            "product_name": product,
            "pack": cell_text(raw_row[col["pack"]]) if "pack" in col and col["pack"] < len(raw_row) else "",
            "opening_stock": opstk,
            "purchase_stock": pur,
            "purchase_free": sp,          # SP = scheme/free on purchase (inflow +)
            "purchase_return": db,        # Db. = debit note (outflow -)
            "sales_qty": sale,
            "sales_free": ss,             # SS = scheme/free on sale (outflow -)
            "sales_return": cr,           # Cr. = credit note (inflow +)
            "closing_stock": cstk,
            "sales_value": num(raw_row, "sval"),
            "closing_stock_value": num(raw_row, "cval"),
        }
        # Signed Adj.: + adds to closing (fold into +sales_return), - subtracts (fold into
        # -sales_free) so the reconcile equation stays exact.
        adj = num(raw_row, "adj")
        if adj > 0:
            rec["sales_return"] = rec["sales_return"] + adj
        elif adj < 0:
            rec["sales_free"] = rec["sales_free"] + (-adj)

        records.append(rec)

    detected = {
        "Item Name": "product_name",
        "Op.": "opening_stock",
        "Pur": "purchase_stock",
        "SP": "purchase_free",
        "Db.": "purchase_return",
        "Sale": "sales_qty",
        "SS": "sales_free",
        "Cr.": "sales_return",
        "C Stk": "closing_stock",
        "SVal": "sales_value",
        "C Val": "closing_stock_value",
    }
    return records, detected
