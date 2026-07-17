"""SwilERP "Sales & Stock Statement" (MEDICINE TRADERS KLM export).

A division-banded grid ("Powered By SwilERP for Retail, Distribution & Chain
Stores") with EXACTLY 7 numeric columns in a fixed order:

    PRODUCT NAME | PACKING | Op.Bal.Qty | Receipt Qty | Free Qty Qty |
                            Total Qty | Issue Qty | Free Qty Qty | Closing Balance

There are TWO "Free Qty Qty" columns that normalize to identical header text, so
the generic ``map_headers_indexed`` binds only one Free column and drops the
other -> ~22% of rows fail the sanity equation (both free quantities are often
fractional: 1.5, 10.5, 4.5, 25...). This parser maps by POSITION off the header,
modelled on ``klm_detailed_stock._column_roles``: each "Free Qty Qty" folds into
the quantity column it FOLLOWS -- the Free after Receipt -> purchase_free, the
Free after Issue -> sales_free. Op.Bal -> opening_stock, Receipt ->
purchase_stock, Issue -> sales_qty, Closing Balance -> closing_stock; the
redundant "Total Qty" (a receipt-side running sum) is ignored.

Reconciliation:

    closing = opening + purchase_stock + purchase_free - sales_qty - sales_free

Division-band lines (single-cell "KLM PHARMA", "KLM PAEDITRIC", ...), the per-
division "TOTAL" rows, the final "GRAND TOTAL", and "*****" separators are
skipped.
"""
from extractors.stock_xlsx.parse_common import cell_text

_NUMERIC = (
    "opening_stock", "purchase_stock", "purchase_free",
    "sales_qty", "sales_free", "closing_stock",
)
_SKIP_TOKENS = ("total", "grand", "*****")


def _num(cell):
    s = cell_text(cell).strip()
    if s in ("", "-"):
        return 0.0
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def _find_header(rows):
    for idx, row in enumerate(rows[:25]):
        labels = [cell_text(c).strip().lower().replace(" ", "") for c in row]
        joined = "".join(labels)
        if (
            "productname" in labels
            and "op.bal.qty." in labels
            and "receiptqty." in labels
            and "issueqty." in labels
            and "closingbalance" in labels
            and labels.count("freeqtyqty") >= 2
        ):
            return idx
        # tolerant fallback: same column set with looser normalization
        if (
            "productname" in joined
            and "op.bal" in joined
            and "receipt" in joined
            and "issue" in joined
            and "closingbalance" in joined
        ):
            return idx
    return None


def _column_roles(header):
    """Assign each column a role. A "Free Qty Qty" column resolves to the field
    of the quantity column it follows (Receipt -> purchase_free, Issue ->
    sales_free). "Total Qty" is deliberately left unmapped (redundant sum)."""
    roles = {}
    free_target = None
    for idx, cell in enumerate(header):
        lab = cell_text(cell).strip().lower().replace(" ", "")
        if lab in ("productname", "product"):
            roles[idx] = "product_name"; free_target = None
        elif lab in ("packing", "pack"):
            roles[idx] = "pack"; free_target = None
        elif lab.startswith("op.bal"):
            roles[idx] = "opening_stock"; free_target = None
        elif lab.startswith("receipt"):
            roles[idx] = "purchase_stock"; free_target = "purchase_free"
        elif lab.startswith("issue"):
            roles[idx] = "sales_qty"; free_target = "sales_free"
        elif lab.startswith("freeqty"):
            if free_target:
                roles[idx] = free_target
            free_target = None
        elif lab.startswith("total"):
            # redundant receipt-side running sum -> ignore
            free_target = None
        elif lab.startswith("closingbalance") or lab == "closing":
            roles[idx] = "closing_stock"; free_target = None
        else:
            free_target = None
    return roles


def parse_medicine_klm_detailed(rows):
    header_idx = _find_header(rows)
    if header_idx is None:
        return [], {}
    roles = _column_roles(rows[header_idx])
    prod_idx = next((i for i, r in roles.items() if r == "product_name"), 0)

    records = []
    for raw in rows[header_idx + 1:]:
        cells = [cell_text(c) for c in raw]
        # Division-band lines are a single populated cell ("KLM PHARMA"); skip.
        populated = [c for c in cells if c.strip()]
        if len(populated) <= 1:
            continue
        product = cells[prod_idx].strip() if prod_idx < len(cells) else ""
        low = product.lower()
        if not product or low.startswith(_SKIP_TOKENS):
            continue
        acc = {k: 0.0 for k in _NUMERIC}
        pack = ""
        skip = False
        for idx, role in roles.items():
            if idx >= len(cells):
                continue
            if role == "pack":
                pack = cells[idx].strip()
            elif role in acc:
                v = _num(cells[idx])
                if v is None:            # a stray non-numeric cell -> not a data row
                    skip = True
                    break
                acc[role] += v
        if skip:
            continue

        record = {"product_name": product}
        if pack:
            record["pack"] = pack
        for key, val in acc.items():
            record[key] = str(int(val)) if val == int(val) else str(val)
        records.append(record)

    detected = {
        "PRODUCT NAME": "product_name", "PACKING": "pack",
        "Op.Bal. Qty.": "opening_stock", "Receipt Qty.": "purchase_stock",
        "Free Qty Qty (after Receipt)": "purchase_free",
        "Issue Qty.": "sales_qty",
        "Free Qty Qty (after Issue)": "sales_free",
        "Closing Balance": "closing_stock",
    }
    return records, detected
