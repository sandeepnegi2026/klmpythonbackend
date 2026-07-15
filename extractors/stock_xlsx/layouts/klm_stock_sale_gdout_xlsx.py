"""KLM (custom ERP) "Stock and Sale for Company: <DIVISION>" export — one .xlsx per
division (SHRI VENKATESH PHARMA: klm cosmo/derma/ped/pharma div stock stat).

Header row (row index ~5, below a 5-row title/address/period band):

    Product | Pack | Op.Stk. | Purch. | PuScm | GD In | Total | Sale | PTS Sl |
    Trfr Out | GD OUT | Sl Scm | Cl Stk | Purch Val | Sale Val | PTS SL VAL |
    Stock Val | Sap Code | Near Exp

Decoded by 100% row reconciliation across all four division exports:

    Cl Stk = Op.Stk. + Purch. + PuScm + GD In
             - Sale - PTS Sl - Trfr Out - GD OUT - Sl Scm

so, in canonical fields:

    Op.Stk.              -> opening_stock
    Purch.               -> purchase_stock
    PuScm  (purch scheme -> purchase_free   (free goods received, inflow)
    GD In  (goods-in     -> purchase_free   (transfer-in, inflow — folded)
    Sale                 -> sales_qty
    PTS Sl (PTS sale     -> sales_free       (outflow — folded)
    Trfr Out (transfer   -> sales_free       (transfer-out, outflow — folded)
    GD OUT (goods-out    -> sales_free       (dispatch-out, outflow — folded)
    Sl Scm (sale scheme  -> sales_free       (free goods issued, outflow)
    Cl Stk               -> closing_stock
    Purch Val            -> purchase_value
    Sale Val             -> sales_value
    Stock Val            -> closing_stock_value
    Sap Code             -> hsn_code

which is exactly opening + purchase + purchase_free - sales - sales_free, matching the
canonical sanity equation. "Total" (a derived Op+Purch running sum), "PTS SL VAL" and
"Near Exp" carry no canonical home and are deliberately left unmapped. The generic
`tabular` reader mis-binds PuScm->sales_free (a 0.88 "contains" hit) and DROPS
Trfr Out / GD OUT / PTS Sl entirely (they lose the sales_qty exact-tie to "Sale"), so
every row with a goods-out movement fails the sanity equation.
"""
from extractors.stock_xlsx.parse_common import cell_text

_NUMERIC = (
    "opening_stock", "purchase_stock", "purchase_free",
    "sales_qty", "sales_free",
    "purchase_value", "sales_value", "closing_stock_value",
)

_SKIP_PREFIXES = (
    "total", "grand", "product", "company", "stock and sale",
    "from ", "shop ", "shri ",
)


def _num(cell):
    """Numeric cell reader: blank / '-' -> 0.0, otherwise the float (None if junk)."""
    s = cell_text(cell).strip()
    if s in ("", "-", "--", "---", ".", "*"):
        return 0.0
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def _compact(cell):
    return cell_text(cell).strip().lower().replace(" ", "").replace(".", "")


def _find_header(rows):
    """The header row: Product | Pack | Op.Stk. | ... | Cl Stk (compact tokens)."""
    for idx, row in enumerate(rows[:25]):
        toks = [_compact(c) for c in row]
        if (
            "product" in toks and "pack" in toks and "opstk" in toks
            and "clstk" in toks and "sale" in toks
            and ("gdout" in toks or "trfrout" in toks)
        ):
            return idx
    return None


def _column_roles(header):
    """Map each column INDEX to a canonical role by its exact compact header token.

    Every value column is bound by EXACT compact text so the OUT-flow columns
    (Trfr Out / GD OUT / PTS Sl), which the generic mapper drops, are folded into
    sales_free, and PuScm is bound to purchase_free (not the wrong sales_free).
    """
    roles = {}
    for idx, cell in enumerate(header):
        tok = _compact(cell)
        if tok == "product":
            roles[idx] = "product_name"
        elif tok == "pack":
            roles[idx] = "pack"
        elif tok == "opstk":
            roles[idx] = "opening_stock"
        elif tok == "purch":
            roles[idx] = "purchase_stock"
        elif tok in ("puscm", "gdin"):        # purchase scheme + goods-in (inflow)
            roles[idx] = "purchase_free"
        elif tok == "sale":
            roles[idx] = "sales_qty"
        elif tok in ("ptssl", "trfrout", "gdout", "slscm"):  # every OUT-flow (outflow)
            roles[idx] = "sales_free"
        elif tok == "clstk":
            roles[idx] = "closing_stock"
        elif tok == "purchval":
            roles[idx] = "purchase_value"
        elif tok == "saleval":
            roles[idx] = "sales_value"
        elif tok == "stockval":
            roles[idx] = "closing_stock_value"
        elif tok == "sapcode":
            roles[idx] = "hsn_code"
        # "total", "ptsslval", "nearexp" deliberately unmapped (derived / no canonical home)
    return roles


def parse_klm_stock_sale_gdout(rows):
    header_idx = _find_header(rows)
    if header_idx is None:
        return [], {}
    roles = _column_roles(rows[header_idx])
    prod_idx = next((i for i, r in roles.items() if r == "product_name"), 0)
    cls_idx = next((i for i, r in roles.items() if r == "closing_stock"), None)
    if cls_idx is None:
        return [], {}

    records = []
    for raw in rows[header_idx + 1:]:
        cells = [cell_text(c) for c in raw]
        if prod_idx >= len(cells):
            continue
        product = cells[prod_idx].strip()
        low = product.lower().replace(" ", "").replace(".", "")
        if not product or low.startswith(_SKIP_PREFIXES):
            continue
        # A footer/section band: one merged text replicated across the row (all cells equal).
        non_empty = [c for c in cells if c.strip()]
        if len(non_empty) > 1 and len(set(non_empty)) == 1:
            continue

        acc = {k: 0.0 for k in _NUMERIC}
        pack = ""
        hsn = ""
        closing = None
        closing_val = None
        skip = False
        for idx, role in roles.items():
            if idx >= len(cells):
                continue
            if role == "product_name":
                continue
            if role == "pack":
                pack = cells[idx].strip()
                continue
            if role == "hsn_code":
                hsn = cells[idx].strip()
                continue
            v = _num(cells[idx])
            if role == "closing_stock":
                if v is None:
                    skip = True
                    break
                closing = v
                continue
            if role == "closing_stock_value":
                closing_val = v or 0.0
                continue
            if v is None:
                skip = True
                break
            if role in acc:
                acc[role] += v
        if skip or closing is None:
            continue

        record = {"product_name": product}
        if pack:
            record["pack"] = pack
        if hsn:
            record["hsn_code"] = hsn
        for key in ("opening_stock", "purchase_stock", "purchase_free",
                    "sales_qty", "sales_free"):
            val = acc[key]
            record[key] = str(int(val)) if val == int(val) else str(val)
        for key in ("purchase_value", "sales_value"):
            val = acc[key]
            record[key] = str(int(val)) if val == int(val) else str(val)
        record["closing_stock"] = (
            str(int(closing)) if closing == int(closing) else str(closing)
        )
        if closing_val is not None:
            record["closing_stock_value"] = (
                str(int(closing_val)) if closing_val == int(closing_val) else str(closing_val)
            )
        records.append(record)

    detected = {
        "Product": "product_name", "Pack": "pack", "Op.Stk.": "opening_stock",
        "Purch.": "purchase_stock", "PuScm": "purchase_free", "GD In": "purchase_free",
        "Sale": "sales_qty", "PTS Sl": "sales_free", "Trfr Out": "sales_free",
        "GD OUT": "sales_free", "Sl Scm": "sales_free", "Cl Stk": "closing_stock",
        "Purch Val": "purchase_value", "Sale Val": "sales_value",
        "Stock Val": "closing_stock_value", "Sap Code": "hsn_code",
    }
    return records, detected
