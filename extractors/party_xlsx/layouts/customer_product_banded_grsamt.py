"""
"<Division>-Sales Report" — G. S. PHARMACEUTICAL DISTRIBUTORS customer/product-wise
sale summary (G.S. DISTRIBUTORS, one workbook per division: KCOSMO, KCOSMOR, KCQ,
KDERMA, KDERMACOR, KPED, KPHARM). The party (customer) is a *band row*, not a column:

    G. S. PHARMACEUTICAL DISTRIBUTORS PVT. LTD.
    KCOSMO-Sales Report-JUNE 2026
    From Date : 01/06/2026 Upto Date : 30/06/2026
    Product Name | Qty | Free | GrsAmt | Area City   <- header (row 5)
    AADARSH MEDICO                                    <- PARTY band (col0 only, no numbers)
    ENZOTRET - TAB | 1 |  | 139.28 | KALWA - E        <- product line under that party
                   | 1 |  | 139.28 | KALWA - E        <- product CONTINUATION (col0 blank,
                                                          same product as the line above)
    AADARSH MEDICO | 2 |  | 278.56                    <- PARTY SUBTOTAL (name+totals, no
                                                          product/area) -> SKIPPED
    AKASH MEDICO                                       <- next PARTY band
    ...
    GRAND TOTAL | 670 |  | 160015.73                  <- report footer -> SKIPPED

Row taxonomy (all four kinds share the same five columns Product Name / Qty / Free /
GrsAmt / Area City):
  * PARTY band     : col0 has a name, every numeric column blank  -> set current party.
  * product line   : col0 has a product name (!= current party) + numbers -> emit.
  * product cont.  : col0 blank + numbers -> emit, carrying the previous product's name.
  * party subtotal : col0 == current party name + numbers, no area  -> skip (double count).
  * grand total /  : "GRAND TOTAL", "(Report End)…", "Prepared by…", "***…" footer -> skip.
    footer lines

The generic ``tabular`` reader maps Product Name/Qty/GrsAmt/Area City correctly but has
no party column to bind, so every row extracts with an empty party_name (-> RED
MISSING_REQUIRED_FIELD:party_name). This layout supplies the one missing piece — the
band carry-down — and skips the per-party subtotals so the summed GrsAmt reconciles to
the report's own printed GRAND TOTAL (verified 0.000% on all seven division books).

``GrsAmt`` is the line gross/net value: mapped to both ``amount`` (what the triage
total-reconcile reads) and the required ``taxable_value``; ``rate`` is derived as
GrsAmt / Qty. ``Area City`` (the vendor's own truncated town) -> ``party_location``.
"""
import re

from core.header_match import map_headers, normalize

from extractors.party_xlsx.parse_common import cell_text, is_subtotal

# The distinctive header signature for this export: the compact tokens of the five column
# cells. "grsamt" + "area city" together are unique across the party_xlsx sample base, so
# the gate cannot steal another vendor's report.
_HEADER_TOKENS = {"productname", "qty", "free", "grsamt", "areacity"}

# Footer / report-furniture lines that trail the grand total.
_FOOTER_RE = re.compile(r"^\s*(grand\s*total|\(report\s*end|prepared\s+by|\*\*\*)", re.IGNORECASE)


def _compact(value):
    return normalize(value).replace(" ", "")


def _header_idx(rows):
    """Row index of the ``Product Name | Qty | Free | GrsAmt | Area City`` header.

    Requires the BANDED five-column signature: ``grsamt`` + ``area city`` + a product
    column present, and — critically — NO customer/party *column*. A columnar sibling
    (KISHORE PHARMACEUTICALS' 21-column register carries the same ``GrsAmt``/``Area
    City``/``Product Name`` tokens but also a real ``Customer Name`` column) maps a
    party_name column and parses correctly via ``tabular``; excluding a mapped
    party_name keeps that file — and any other columnar variant — off this reader.
    """
    for idx, row in enumerate(rows[:30]):
        cells = [cell_text(c) for c in row]
        toks = {_compact(c) for c in cells if c}
        if not ({"grsamt", "areacity"} <= toks and ("productname" in toks or "product" in toks)):
            continue
        keys = {info["canonical"] for info in map_headers(cells, "party").values()}
        if "party_name" in keys:
            # Columnar register (party is a real column) -> not this banded layout.
            continue
        return idx
    return None


def detect(rows):
    """True only for the G.S. DISTRIBUTORS division sale report.

    Gated on the banded five-column header (``grsamt`` AND ``area city`` present, a
    product column present, and NO customer/party column). The ``GrsAmt``/``Area
    City`` pairing without a party column is unique to this vendor, so no other
    party_xlsx layout is diverted.
    """
    return _header_idx(rows) is not None


def _to_float(value):
    text = cell_text(value).replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_customer_product_banded_grsamt(rows):
    header_idx = _header_idx(rows)
    if header_idx is None:
        return [], {}

    records = []
    current_party = ""
    last_product = ""
    for raw in rows[header_idx + 1 :]:
        cells = [cell_text(c) for c in raw]
        first = cells[0].strip() if cells else ""
        qty = cells[1] if len(cells) > 1 else ""
        # cells[2] is the (always-blank here) Free column.
        amount = cells[3] if len(cells) > 3 else ""
        area = cells[4] if len(cells) > 4 else ""
        has_numbers = bool(qty.strip() or amount.strip())

        if _FOOTER_RE.match(first):
            # GRAND TOTAL and everything after it (report-end / prepared-by / disclaimer).
            break

        # PARTY band: a name in col0 with no numeric figures.
        if first and not has_numbers:
            if is_subtotal(first):
                continue
            current_party = first
            last_product = ""
            continue

        # Per-party subtotal: col0 repeats the current party's name and carries totals but
        # no product/area. Skip so its value is not double-counted against the grand total.
        if first and has_numbers and first.strip().lower() == current_party.strip().lower():
            continue

        if not has_numbers:
            continue

        # Product line (col0 = product name) or its continuation (col0 blank -> reuse the
        # previous product's name).
        product = first or last_product
        if not product or is_subtotal(product):
            continue
        if first:
            last_product = first
        if not current_party:
            continue

        record = {
            "party_name": current_party,
            "product_name": product,
            "qty": qty,
            "amount": amount,
            # No rate/taxable column in this export; GrsAmt is the line net value.
            "taxable_value": amount,
        }
        if area:
            record["party_location"] = area
        amt_f, qty_f = _to_float(amount), _to_float(qty)
        if amt_f is not None and qty_f:
            record["rate"] = round(amt_f / qty_f, 4)
        records.append(record)

    detected = {
        "Product Name": "product_name",
        "Qty": "qty",
        "Free": "free_qty",
        "GrsAmt": "amount",
        "Area City": "party_location",
    }
    return records, detected
