"""KLM (custom ERP) "Stock And Sale" export — YOGIRAM DISTRIBUTORS, one .xls per division.

Header row (row index ~5, below a 5-row title/address/period/generated band):

    CompCode | Company | Code | Item | Pack | Apr | Mar | Op. | Pur. | SP | Pur Ret |
    SPur Ret | TRR | Sale | SS | TRI | SRet | Adj. | Cls.Stk | Net Sale

Blank cells and "-" mean zero. The two prior-month columns (Apr/Mar) are last-month sale
qtys (informational) and "Net Sale" is a rupee VALUE — none of these are stock movement,
so a naive tabular reader that maps Apr/Mar/Net Sale onto quantity fields (or drops the
SP/SS free columns) fails the sanity equation. Value columns are printed only as footer
grand-totals (Opening Val / Purchase / Sales / Closing / Pur.Ret Val / Sales Ret Val), not
per row.

Decoded by 100% row reconciliation across the samples:

    Cls.Stk = Op. + Pur. + SP - Pur Ret - Sale - SS + SRet - TRI + TRR

so, in canonical fields:

    SP           -> purchase_free   (free goods received, inflow)
    SS           -> sales_free      (free goods issued, outflow)
    SRet / TRR   -> sales_return    (returns received back in, inflow)
    Pur Ret /
      SPur Ret   -> purchase_return (goods returned to supplier, outflow)
    TRI          -> sales_free      (stock transferred out, outflow)
    Adj.         -> signed: +ve folds into sales_return (in), -ve into purchase_return (out)

which is exactly opening + purchase + purchase_free - purchase_return - sales - sales_free
+ sales_return, identical to the KLM pdf side and to klm_detailed_stock. SPur Ret / TRR /
TRI / Adj. are all-dash (zero) in almost every row; TRI carried one real transfer-out.
"""
from extractors.stock_xlsx.parse_common import cell_text

_NUMERIC = (
    "opening_stock", "purchase_stock", "purchase_free", "purchase_return",
    "sales_qty", "sales_free", "sales_return",
)

_SKIP_PREFIXES = (
    "total", "grand", "company", "division", "compcode", "item", "code",
    "sale(", "closing ", "opening val", "generated", "from :", "stock and sale",
)


def _num(cell):
    """Numeric cell reader: blank / '-' / '.' -> 0.0, otherwise the float (None if junk)."""
    s = cell_text(cell).strip()
    if s in ("", "-", "--", "---", ".", "*"):
        return 0.0
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def _find_header(rows):
    """The header is the row whose first cells are CompCode | Company | Code | Item | Pack."""
    for idx, row in enumerate(rows[:25]):
        labels = [cell_text(c).strip().lower() for c in row]
        compact = [l.replace(" ", "").replace(".", "") for l in labels]
        if (compact[:5] == ["compcode", "company", "code", "item", "pack"]
                and "op" in compact and "clsstk" in compact and "sale" in compact):
            return idx
    return None


def _column_roles(header):
    """Map each column INDEX to a canonical role by its exact compact header token.

    Matching is exact (not substring) so "SPur Ret" (spurret) cannot be swallowed by the
    "Pur Ret" (purret) rule, and the two prior-month sale columns / rupee "Net Sale" value
    column are deliberately left unmapped (they are not stock movement).
    """
    roles = {}
    for idx, cell in enumerate(header):
        tok = cell_text(cell).strip().lower().replace(" ", "").replace(".", "").replace("`", "")
        if tok == "item":
            roles[idx] = "product_name"
        elif tok == "pack":
            roles[idx] = "pack"
        elif tok in ("op", "opstk", "openstk"):
            roles[idx] = "opening_stock"
        elif tok in ("pur", "purc"):
            roles[idx] = "purchase_stock"
        elif tok == "sp":                       # scheme / free purchase (free goods in)
            roles[idx] = "purchase_free"
        elif tok in ("purret", "spurret"):      # purchase return + scheme purchase return
            roles[idx] = "purchase_return"
        elif tok in ("trr",):                   # transfer return (inflow)
            roles[idx] = "sales_return"
        elif tok == "sale":
            roles[idx] = "sales_qty"
        elif tok == "ss":                       # scheme / free sale (free goods out)
            roles[idx] = "sales_free"
        elif tok in ("tri",):                   # transfer issue (outflow)
            roles[idx] = "sales_free"
        elif tok in ("sret", "sret."):          # sales return (inflow)
            roles[idx] = "sales_return"
        elif tok in ("adj", "adj."):
            roles[idx] = "adj"
        elif tok in ("clsstk", "closingstk", "clsstk."):
            roles[idx] = "closing_stock"
    return roles


def parse_klm_stock_and_sale(rows):
    header_idx = _find_header(rows)
    if header_idx is None:
        return [], {}
    roles = _column_roles(rows[header_idx])
    prod_idx = next((i for i, r in roles.items() if r == "product_name"), 3)
    pack_idx = next((i for i, r in roles.items() if r == "pack"), None)
    cls_idx = next((i for i, r in roles.items() if r == "closing_stock"), None)

    records = []
    for raw in rows[header_idx + 1:]:
        cells = [cell_text(c) for c in raw]
        if prod_idx >= len(cells):
            continue
        product = cells[prod_idx].strip()
        low = product.lower().replace(" ", "").replace(".", "")
        if not product or low.startswith(_SKIP_PREFIXES):
            continue
        # A footer/section band is one merged text repeated across the row (all cells equal),
        # or a row with no numeric closing cell.
        non_empty = [c for c in cells if c.strip()]
        if len(non_empty) > 1 and len(set(non_empty)) == 1:
            continue

        acc = {k: 0.0 for k in _NUMERIC}
        pack = ""
        adj = 0.0
        closing = None
        skip = False
        for idx, role in roles.items():
            if idx >= len(cells):
                continue
            if role == "product_name":
                continue
            if role == "pack":
                pack = cells[idx].strip()
                continue
            v = _num(cells[idx])
            if role == "closing_stock":
                if v is None:
                    skip = True
                    break
                closing = v
                continue
            if v is None:
                # a stray non-numeric cell in a quantity column -> not a real data row
                skip = True
                break
            if role == "adj":
                adj += v
            elif role in acc:
                acc[role] += v
        if skip or closing is None:
            continue

        # Signed "Adj." — positive is an inflow (added like a return), negative an outflow.
        if adj >= 0:
            acc["sales_return"] += adj
        else:
            acc["purchase_return"] += -adj

        record = {"product_name": product}
        if pack:
            record["pack"] = pack
        for key, val in acc.items():
            record[key] = str(int(val)) if val == int(val) else str(val)
        record["closing_stock"] = str(int(closing)) if closing == int(closing) else str(closing)
        records.append(record)

    detected = {
        "Item": "product_name", "Pack": "pack", "Op.": "opening_stock",
        "Pur.": "purchase_stock", "SP": "purchase_free", "Pur Ret": "purchase_return",
        "SPur Ret": "purchase_return", "TRR": "sales_return", "Sale": "sales_qty",
        "SS": "sales_free", "TRI": "sales_free", "SRet": "sales_return",
        "Adj.": "sales_return/purchase_return", "Cls.Stk": "closing_stock",
    }
    return records, detected
