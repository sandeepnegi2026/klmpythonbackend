"""
"Selected sale types, companies: product-wise, area-wise sale/DC summary" — a KLM/Marg
(MediVision Platinum) *pivot* export seen from FLORA AGENCIES. There is no customer column
at all: the report is one row per product, with the sale broken out across a wide band of
per-area column PAIRS::

    Product | Unit | Comp | <AREA-1> qty | <AREA-1> amt | <AREA-2> qty | <AREA-2> amt | ...
            | Total qty | Total amount

Every non-blank ``<AREA> qty``/``<AREA> amt`` cell on a product row is a (product, area)
sale of that quantity for that rupee amount. The area/route is the only party-level
dimension the report carries, so it becomes ``party_name`` (and ``party_location``) — this
mirrors how the other area-wise summaries in this route treat the route as the customer
grain. ``Comp`` is the KLM division code ("KLM Qcosmo", "KLM Dermac", "KLM Cosmo",
"KLM COSCOR", ...), emitted as ``division``.

The parser UNPIVOTS the area column pairs into one record each, EXCLUDING the trailing
``Total qty``/``Total amount`` pair (that is the row's own sum — emitting it would double
count) and skipping the printed per-column "Totals:" footer row and the "Generated at ..."
line. This clears MISSING_REQUIRED_FIELD:party_name (no generic layout maps the pivoted
area cells to a party) and yields complete qty + amount per (product, area).

No free-qty, bill or date columns exist in this report, so those canonical fields are left
for ``enforce_schema`` to default.
"""
from core.header_match import normalize

from extractors.party_xlsx.parse_common import cell_text


def _find_header_idx(rows):
    """Return the index of the ``Product | Unit | Comp | ... | Total ...`` header row.

    Identified structurally: a row whose cells contain a ``product`` header, a ``comp``
    header, and at least one ``<x> qty``/``<x> amt`` pair — the fingerprint of this pivot.
    """
    for idx, row in enumerate(rows[:20]):
        cells = [normalize(c) for c in row]
        if "product" not in cells or "comp" not in cells:
            continue
        has_qty_pair = any(c.endswith(" qty") for c in cells) and any(
            c.endswith(" amt") for c in cells
        )
        if has_qty_pair:
            return idx
    return None


def _area_pairs(headers):
    """Collect (area_name, qty_idx, amt_idx) tuples from the wide header, EXCLUDING the
    trailing ``Total qty``/``Total amount`` summary pair.

    Areas are keyed off the `` <AREA> qty`` header (case preserved from the raw cell); its
    matching ``<AREA> amt`` sits at the next index (amt columns immediately follow their qty
    column in this export). Both the qty and the amt header carry the same area prefix, so
    the area name is derived from the raw ``qty`` header by stripping the trailing " qty".
    """
    n = len(headers)
    pairs = []
    for idx, raw in enumerate(headers):
        low = cell_text(raw).strip().lower()
        if not low.endswith(" qty"):
            continue
        area = cell_text(raw).strip()[: -len(" qty")].strip()
        if not area or area.lower() == "total":
            # skip the row-sum "Total qty" pair (double counting) and any blank prefix
            continue
        amt_idx = None
        # matching amt column: prefer "<AREA> amt" by name, else the adjacent column.
        want = (area + " amt").lower()
        for j in range(idx + 1, n):
            if cell_text(headers[j]).strip().lower() == want:
                amt_idx = j
                break
        if amt_idx is None and idx + 1 < n:
            nxt = cell_text(headers[idx + 1]).strip().lower()
            if nxt.endswith(" amt") and not nxt.startswith("total"):
                amt_idx = idx + 1
        pairs.append((area, idx, amt_idx))
    return pairs


def detect(rows):
    return _find_header_idx(rows) is not None


def parse_product_areawise_pivot(rows):
    header_idx = _find_header_idx(rows)
    if header_idx is None:
        return [], {}
    headers = [cell_text(c) for c in rows[header_idx]]

    # Fixed leading columns.
    col_product = col_unit = col_comp = None
    for idx, raw in enumerate(headers):
        low = normalize(raw)
        if col_product is None and low == "product":
            col_product = idx
        elif col_unit is None and low in ("unit", "pack", "packing"):
            col_unit = idx
        elif col_comp is None and low in ("comp", "company", "division"):
            col_comp = idx
    if col_product is None:
        return [], {}

    pairs = _area_pairs(headers)
    if not pairs:
        return [], {}

    records = []
    for raw in rows[header_idx + 1:]:
        if not raw:
            continue
        product = cell_text(raw[col_product]) if col_product < len(raw) else ""
        if not product:
            # Footer "Totals:" row (product col blank, label sits in an area col) or the
            # "Generated at ..." trailer — never a product line.
            continue
        if normalize(product).startswith("total"):
            continue
        pack = cell_text(raw[col_unit]) if (col_unit is not None and col_unit < len(raw)) else ""
        division = cell_text(raw[col_comp]) if (col_comp is not None and col_comp < len(raw)) else ""
        # The workbook's "Generated at ... using MediVision Platinum" trailer (and any similar
        # full-width banner) is unmerged into an IDENTICAL value across every cell, so the
        # product cell equals the Comp cell. A genuine product row never has product == comp
        # (division) — use that to drop the banner without touching real items.
        if division and product == division:
            continue

        for area, qty_idx, amt_idx in pairs:
            qty = cell_text(raw[qty_idx]) if qty_idx < len(raw) else ""
            amt = cell_text(raw[amt_idx]) if (amt_idx is not None and amt_idx < len(raw)) else ""
            if not qty and not amt:
                continue  # blank area cell — no sale of this product in this area
            record = {
                "product_name": product,
                "pack": pack,
                "division": division,
                "party_name": area,
                "party_location": area,
                "qty": qty,
                "amount": amt,
                # amount is the clean rupee value of the (product, area) sale; expose it as
                # taxable_value too so the value-based required field is populated rather
                # than defaulted to 0 (there is no rate column to derive it from).
                "taxable_value": amt,
            }
            records.append(record)

    detected = {
        headers[col_product]: "product_name",
    }
    if col_unit is not None:
        detected[headers[col_unit]] = "pack"
    if col_comp is not None:
        detected[headers[col_comp]] = "division"
    for area, qty_idx, amt_idx in pairs:
        detected[headers[qty_idx]] = "qty"
        if amt_idx is not None:
            detected[headers[amt_idx]] = "amount"
    return records, detected
