"""KLM product *order* form (XLS) — PHARMA ASIA DISTRIBUTOR "klm order.xls".

Structure::

        | PHARMA ASIA DISTRIBUTOR                         <- ordering party (col1, row 0)
        | ORDER DATE       |    | 2026-06-29 00:00:00     <- order date
    Code | Product Description | Packing                  <- header (NO qty/value col)
    139  | KLM ( DERMA )                                  <- division band (code + name, col2 blank)
    2439 | CANROLFIN CREAM  | 15GM                        <- catalog line, NOT ordered (no col3)
    2440 | CANROLFIN CREAM  | 30GM   | 10                 <- ORDERED line (col3 = order qty)
    ...

This is an order placed BY the distributor: the whole KLM catalog is listed and the
ordered items carry a quantity in an unheadered 4th column. The header maps only Code/
Product Description/Packing (no party, no qty, no value) so ``detect_header_row`` fires and
``tabular`` emits every catalog row with party_name blank and all numerics zero -> RED
(MISSING_REQUIRED_FIELD party_name + every core numeric zero).

This parser:
  * reads the ordering party from the title row (col1 of the first non-empty row above
    the ``Code | Product Description | Packing`` header),
  * emits ONLY the lines that carry an order quantity in the 4th column (the party's real
    order), never the un-ordered catalog tail (which has no data),
  * maps the 4th column POSITIONALLY to ``qty`` — a genuine order quantity, NOT derived
    from any value column (this report prints no value/amount column at all),
  * carries the ``KLM ( <DIV> )`` band down as ``division``.

Title-gated on the compact "order date" + exact "Code Product Description Packing" header
run, which no other corpus file carries, so it can only ever claim this order-form export.
"""
import re

from extractors.party_xlsx.parse_common import cell_text, compact, is_numeric_qty

# Compact tokens of the two-part fingerprint: the "ORDER DATE" banner plus the exact
# three-cell header run. Both must be present, so a plain sale/stock export that happens
# to print a "Packing" column (there are many) can never match.
_ORDER_TOKEN = "orderdate"
_HEADER_TOKEN = "codeproductdescriptionpacking"

# A division band row: "KLM ( DERMA )" / "KLM(COSMO DIV)" / "KLM(PHARMA DIV)". The KLM
# prefix (optionally glued to the paren) marks a grouping row, not a product.
_DIV_BAND_RE = re.compile(r"^\s*KLM\s*[(\-]", re.IGNORECASE)


def _header_idx(rows):
    for idx, row in enumerate(rows[:12]):
        cells = [cell_text(c).strip().lower() for c in row]
        if "code" in cells and "product description" in cells and "packing" in cells:
            return idx
    return None


def detect(rows):
    blob = compact(" ".join(" ".join(cell_text(c) for c in r) for r in rows[:8]))
    if _ORDER_TOKEN not in blob or _HEADER_TOKEN not in blob:
        return False
    return _header_idx(rows) is not None


def _order_party(rows, header_idx):
    """The ordering party sits in the title band above the header (col1 of the first
    non-empty row that is not the ORDER DATE line)."""
    for row in rows[:header_idx]:
        cells = [cell_text(c) for c in row]
        text = " ".join(c for c in cells if c).strip()
        if not text:
            continue
        low = text.lower()
        if low.startswith("order date") or low.startswith("order-date"):
            continue
        # first non-empty cell after any leading blank columns
        for c in cells:
            if c.strip():
                return c.strip()
    return ""


def _division(name):
    """`KLM ( DERMA )` / `KLM(COSMO DIV)` -> the inner division text."""
    inner = re.search(r"\(([^)]*)\)", name)
    div = inner.group(1) if inner else re.sub(r"^\s*KLM\s*[-]?\s*", "", name, flags=re.I)
    return re.sub(r"\bDIV\b\.?", "", div, flags=re.I).strip(" .-")


def parse_klm_order_form_xlsx(rows):
    header_idx = _header_idx(rows)
    if header_idx is None:
        return [], {}
    header = [cell_text(c).strip().lower() for c in rows[header_idx]]
    col = {}
    for j, h in enumerate(header):
        if h == "code":
            col["code"] = j
        elif h == "product description":
            col["product"] = j
        elif h == "packing":
            col["pack"] = j
    if "product" not in col:
        return [], {}
    # The order-quantity column sits immediately to the RIGHT of Packing (unheadered).
    qty_idx = col.get("pack", col["product"]) + 1

    party = _order_party(rows, header_idx)
    division = ""
    records = []
    for raw in rows[header_idx + 1:]:
        cells = [cell_text(c) for c in raw]

        def _get(key):
            i = col.get(key)
            return cells[i].strip() if (i is not None and i < len(cells)) else ""

        name = _get("product")
        if not name:
            continue
        pack = _get("pack")
        # Division band: KLM (...) grouping row (no packing, no order qty).
        if not pack and _DIV_BAND_RE.match(name):
            division = _division(name)
            continue
        qty = cells[qty_idx].strip() if qty_idx < len(cells) else ""
        # Thousands-grouped order qty ("1,000" / "1,00,000"): strip the grouping
        # commas so the numeric gate below accepts it (pandas to_numeric rejects
        # grouped commas). Only when the comma-less form is all digits, so "10+2"
        # scheme annotations, dates and codes are left byte-identical and still skip.
        if "," in qty and qty.replace(",", "").isdigit():
            qty = qty.replace(",", "")
        # Emit only genuinely ordered lines; skip the un-ordered catalog tail and any
        # stray date cell that landed in the qty column.
        if not qty or not is_numeric_qty(qty):
            continue
        rec = {
            "party_name": party,
            "product_name": name,
            "pack": pack,
            "qty": qty,
        }
        if division:
            rec["division"] = division
        code = _get("code")
        if code:
            rec["hsn_code"] = code
        records.append(rec)

    detected = {
        "PHARMA ASIA DISTRIBUTOR": "party_name",
        "Product Description": "product_name",
        "Packing": "pack",
        "Order Qty": "qty",
    }
    return records, detected
