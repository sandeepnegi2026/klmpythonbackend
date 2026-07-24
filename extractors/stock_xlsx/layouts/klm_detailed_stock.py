"""KLM "DETAILED" stock statement (VENKATA SAI AGENCIES export).

A clean grid whose header pairs a "Free" column AFTER every quantity column:

    Item | Pack | Opening | Purchase | Free | P.Return | Free | Sale | Free | S.Return | Free | Others | Closing | Age Of Item | Barcode

The four identical "Free" headers defeat the generic ``map_headers_indexed`` (it can bind
only one column to purchase_free and one to sales_free), so purchase_free, sales_free and
the signed "Others" adjustment are dropped — leaving ~52% of rows failing the sanity
equation. This parser maps by POSITION off the header instead: each "Free" folds into the
quantity column it follows, and "Others" folds by sign. With

    closing = opening + purchase + purchase_free − purchase_return − sales − sales_free + sales_return

(where purchase_return absorbs P.Return + its Free and a NEGATIVE Others; sales_return
absorbs S.Return + its Free and a POSITIVE Others) every one of the 240 real rows
reconciles exactly.
"""
from extractors.stock_xlsx.parse_common import cell_text

_NUMERIC = (
    "opening_stock", "purchase_stock", "purchase_free", "purchase_return",
    "sales_qty", "sales_free", "sales_return", "closing_stock",
)
_SKIP_PREFIXES = ("division", "company", "total", "grand", "item", "date ", "date:")


def _num(cell):
    s = cell_text(cell).strip()
    if s in ("", "-"):
        return 0.0
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def _find_header(rows):
    for idx, row in enumerate(rows[:20]):
        labels = [cell_text(c).strip().lower() for c in row]
        if ("item" in labels and "opening" in labels and "closing" in labels
                and any(l == "purchase" for l in labels)
                and any("age of item" in l for l in labels)):
            return idx
    return None


def _column_roles(header):
    """Assign each column a role. A "Free" column resolves to the field of the quantity
    column it follows (Purchase→purchase_free, P.Return→purchase_return, Sale→sales_free,
    S.Return→sales_return)."""
    roles = {}
    free_target = None
    for idx, cell in enumerate(header):
        lab = cell_text(cell).strip().lower().replace(" ", "")
        if lab == "item":
            roles[idx] = "product_name"; free_target = None
        elif lab == "pack":
            roles[idx] = "pack"; free_target = None
        elif lab == "opening":
            roles[idx] = "opening_stock"; free_target = None
        elif lab == "purchase":
            roles[idx] = "purchase_stock"; free_target = "purchase_free"
        elif lab in ("p.return", "preturn", "p.retrun"):
            roles[idx] = "purchase_return"; free_target = "purchase_return"
        elif lab == "sale":
            roles[idx] = "sales_qty"; free_target = "sales_free"
        elif lab in ("s.return", "sreturn"):
            roles[idx] = "sales_return"; free_target = "sales_return"
        elif lab == "free":
            if free_target:
                roles[idx] = free_target
            free_target = None
        elif lab == "others":
            roles[idx] = "others"; free_target = None
        elif lab == "closing":
            roles[idx] = "closing_stock"; free_target = None
        elif lab == "barcode":
            roles[idx] = "barcode"; free_target = None
        else:
            free_target = None
    return roles


def parse_klm_detailed_stock(rows):
    header_idx = _find_header(rows)
    if header_idx is None:
        return [], {}
    roles = _column_roles(rows[header_idx])
    prod_idx = next((i for i, r in roles.items() if r == "product_name"), 0)

    records = []
    for raw in rows[header_idx + 1:]:
        cells = [cell_text(c) for c in raw]
        product = cells[prod_idx].strip() if prod_idx < len(cells) else ""
        low = product.lower()
        if not product or low.startswith(_SKIP_PREFIXES) or "highlighted in red" in low:
            continue
        acc = {k: 0.0 for k in _NUMERIC}
        pack = barcode = ""
        others = 0.0
        skip = False
        for idx, role in roles.items():
            if idx >= len(cells):
                continue
            if role == "pack":
                pack = cells[idx].strip()
            elif role == "barcode":
                barcode = cells[idx].strip()
            elif role == "others":
                others = _num(cells[idx]) or 0.0
            elif role in acc:
                v = _num(cells[idx])
                if v is None:            # a stray non-numeric cell -> not a data row
                    skip = True
                    break
                acc[role] += v
        if skip:
            continue
        # Signed "Others" adjustment: positive is an inflow (fold into sales_return, which
        # the equation adds), negative is an outflow (fold into purchase_return, subtracted).
        if others >= 0:
            acc["sales_return"] += others
        else:
            acc["purchase_return"] += -others

        record = {"product_name": product}
        if pack:
            record["pack"] = pack
        if barcode:
            record["barcode"] = barcode
        for key, val in acc.items():
            record[key] = str(int(val)) if val == int(val) else str(val)
        records.append(record)

    detected = {
        "Item": "product_name", "Pack": "pack", "Opening": "opening_stock",
        "Purchase": "purchase_stock", "Purchase Free": "purchase_free",
        "P.Return (+free)": "purchase_return", "Sale": "sales_qty",
        "Sale Free": "sales_free", "S.Return (+free)": "sales_return",
        "Others (signed)": "sales_return/purchase_return", "Closing": "closing_stock",
    }
    return records, detected
