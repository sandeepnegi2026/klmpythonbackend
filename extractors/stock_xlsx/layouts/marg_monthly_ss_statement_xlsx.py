"""Marg/KLM PALANPUR "MONTHLY STOCK & SALES STATEMENT" (.xls) — AAKASH DISTRIBUTORS.

The sheet is banded by Make/division (KLCOSMOCOR, KLDERMACOR, …). Each band repeats a
two-row column header:

    Code | * | Product | Pack | Opening Qty | Purchase Qty | Goods Ret. | Total In Qty |
    Sale Qty | Purc. Ret. Qty | Balance Qty | Order 1 (Qty/Free) | Order 2 (Qty/Free) | Remarks

and closes with a "Total value :-" control-total row carrying rupee VALUE totals.

Reconciliation printed by the report:

    Balance = Opening + Purchase + GoodsRet − Sale − PurcRet

where "Goods Ret." is a sales-return INFLOW that ADDS to stock and "Purc. Ret." is a
purchase-return OUTFLOW that SUBTRACTS. "Total In Qty" (= Opening + Purchase + GoodsRet)
is a DERIVED column and must NOT be mapped to any movement field, or the equation
double-counts. Order 1 / Order 2 (Qty/Free) are pending-order columns, not stock free.

Field mapping is chosen to satisfy the engine's own stock sanity equation
(core postprocess):

    closing = opening + purchase + purchase_free − purchase_return − sales − sales_free − sales_return

So the inflow "Goods Ret." folds into ``purchase_free`` (an ADDED term) and the outflow
"Purc. Ret." into ``purchase_return`` (a SUBTRACTED term); every genuine row then
reconciles exactly.

Why positional-off-header rather than the generic tabular reader: the export scatters
each logical column across a fixed but sparse set of spreadsheet columns (blank spacer
cells between every value), and the coarse ``map_headers_indexed`` binds only the first
column whose text matches a synonym. Here we read the band header once, resolve each
label to its column index, and read data rows by those indexes — robust to the spacer
columns and to the repeated per-band headers.
"""
from extractors.stock_xlsx.parse_common import cell_text

# canonical numeric movement fields this layout populates
_NUMERIC = (
    "opening_stock", "purchase_stock", "purchase_free",
    "purchase_return", "sales_qty", "closing_stock",
)

# section / control rows whose first text cell must NOT be treated as a product
_SKIP_PREFIXES = (
    "make", "code", "total value", "total on sale", "total", "grand",
    "company", "division", "manufacturer", "period", "page", "for ",
)


def _num(cell):
    """Parse a quantity/value cell. Blank / dash → 0.0; a stray non-numeric → None
    (signals a non-data row so the caller can skip it)."""
    s = cell_text(cell).strip().replace(",", "")
    if s in ("", "-", "-----"):
        return 0.0
    # strip a trailing per-row flag like "5 H" (batch/hold marker seen in Remarks bleed)
    s = s.split()[0] if " " in s else s
    try:
        return float(s)
    except ValueError:
        return None


def _find_header(rows):
    """Locate the FIRST band header row and return (index, column-index map).

    Keyed on the distinctive Marg SS-statement column set. Returns a dict mapping
    canonical field -> spreadsheet column index. Only movement columns we keep are
    mapped; Total In Qty / Order 1 / Order 2 / Remarks are deliberately ignored.
    """
    for idx, row in enumerate(rows[:80]):
        joined = " ".join(cell_text(c) for c in row).lower()
        j = joined.replace("\n", " ")
        if not ("opening" in j and "goods ret" in j and "balance" in j
                and "purc. ret" in j and "sale" in j):
            continue
        colmap = {}
        prod_idx = None
        for cidx, cell in enumerate(row):
            lab = cell_text(cell).strip().lower().replace("\n", " ")
            lab = " ".join(lab.split())  # collapse internal whitespace
            if lab == "product":
                prod_idx = cidx
            elif lab.startswith("opening"):
                colmap.setdefault("opening_stock", cidx)
            elif lab.startswith("purchase"):
                colmap.setdefault("purchase_stock", cidx)
            elif lab.startswith("goods ret"):
                colmap.setdefault("purchase_free", cidx)  # inflow → ADDED term
            elif lab.startswith("sale"):
                colmap.setdefault("sales_qty", cidx)
            elif lab.startswith("purc. ret") or lab.startswith("purc ret"):
                colmap.setdefault("purchase_return", cidx)  # outflow → SUBTRACTED term
            elif lab.startswith("balance"):
                colmap.setdefault("closing_stock", cidx)
            elif lab == "pack":
                colmap.setdefault("pack", cidx)
            elif lab == "code":
                colmap.setdefault("code", cidx)
        if prod_idx is not None and "opening_stock" in colmap and "closing_stock" in colmap:
            colmap["product_name"] = prod_idx
            return idx, colmap
    return None, None


def _is_header_repeat(cells, colmap):
    """A per-band header reprinted mid-sheet (Code / Product / Opening…)."""
    prod = cells[colmap["product_name"]].strip().lower() if colmap["product_name"] < len(cells) else ""
    return prod == "product"


def parse_marg_monthly_ss_statement_xlsx(rows):
    header_idx, colmap = _find_header(rows)
    if header_idx is None:
        return [], {}

    prod_idx = colmap["product_name"]
    code_idx = colmap.get("code")
    pack_idx = colmap.get("pack")

    records = []
    for raw in rows[header_idx + 1:]:
        cells = [cell_text(c) for c in raw]
        product = cells[prod_idx].strip() if prod_idx < len(cells) else ""
        low = product.lower()
        if not product or low.startswith(_SKIP_PREFIXES):
            continue
        # a "Total value :-" / "Make :" control row keeps its label in a non-product cell,
        # leaving the product column blank — already skipped above via empty product.

        acc = {k: 0.0 for k in _NUMERIC}
        skip = False
        for field in _NUMERIC:
            cidx = colmap.get(field)
            if cidx is None or cidx >= len(cells):
                continue
            v = _num(cells[cidx])
            if v is None:  # a non-numeric value in a quantity column → not a data row
                skip = True
                break
            acc[field] = v
        if skip:
            continue

        record = {"product_name": product}
        code = cells[code_idx].strip() if (code_idx is not None and code_idx < len(cells)) else ""
        if code:
            record["hsn_code"] = code
        pack = cells[pack_idx].strip() if (pack_idx is not None and pack_idx < len(cells)) else ""
        if pack:
            record["pack"] = pack
        for key, val in acc.items():
            record[key] = str(int(val)) if val == int(val) else str(val)
        records.append(record)

    detected = {
        "Code": "hsn_code",
        "Product": "product_name",
        "Pack": "pack",
        "Opening Qty": "opening_stock",
        "Purchase Qty": "purchase_stock",
        "Goods Ret.": "purchase_free",
        "Sale Qty": "sales_qty",
        "Purc. Ret. Qty": "purchase_return",
        "Balance Qty": "closing_stock",
    }
    return records, detected
