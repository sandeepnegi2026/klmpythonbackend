"""
SENTHIL PHARMA "Area-wise" columnar sale export (KLM per-division AREAWISE books).

A wide COLUMNAR report — one row per (product, customer) sale — whose party sits in a
``CUSTOMER NAME`` column, interleaved with ``AREA NAME :`` / ``COMPANY NAME :`` section
headers and ``GROUP TOTAL <area>`` subtotal rows:

    PRODUCT NAME | PRODUCT CODE | PACKING | QTY | FREE QTY | GOODS VALUE | CUSTOMER NAME | INVNO | ...
    COMPANY NAME : KLM COSMO                                                                        <- header (no customer)
    AREA NAME : TIRUPUR(...)                                                                        <- area header (no customer)
    EKRAN AQUA GEL      | ... | 277.97 | ALM MEDICALS-TIRUPUR  BAZAAR-TIRUPUR | GP008224            <- real sale
    GROUP TOTAL TIRUPUR | ...       793.22 |                                                        <- subtotal (no customer)

``partywise_band`` mis-claims it and reads the "Report Heading:" masthead / area serials as the
party for a handful of rows; the naive columnar/tabular reader instead forward-fills the party onto
the ``GROUP TOTAL`` subtotal rows and DOUBLE-COUNTS the value (~4.7x). The clean rule: a real sale is
exactly the row whose ``CUSTOMER NAME`` cell is populated — the section headers and subtotals leave it
blank. This reader maps columns by their printed header names and emits only CUSTOMER-NAME rows, so the
value reconciles to the same 98,260.85 the band reader already reported, but with the true customer.

Gated on the exact "PRODUCT NAME PRODUCT CODE ... GOODS VALUE CUSTOMER NAME" header run (unique to this
export), detected BEFORE partywise_band.
"""
from extractors.party_xlsx.parse_common import cell_text, compact

# canonical role  <-  compacted header-cell label
_ROLE = {
    "productname": "product_name",
    "packing": "pack",
    "qty": "qty",
    "freeqty": "free_qty",
    "goodsvalue": "amount",
    "customername": "party_name",
    "invno": "invoice_number",
}
_SUBTOTAL_PREFIXES = ("GROUP TOTAL", "AREA NAME", "COMPANY NAME", "GRAND TOTAL", "TOTAL")


def _header_idx(rows):
    # SENTHIL-specific header run: PRODUCT NAME | PRODUCT CODE | PACKING | ... | GOODS VALUE |
    # CUSTOMER NAME. Requiring the "product name -> product code -> packing" prefix (which the
    # GOWRI "Bill Date | MFR Name | Customer Name | Address | Pin | Product Name" columnar export
    # lacks) keeps that already-correct sibling on `tabular`.
    for i, row in enumerate(rows[:12]):
        c = compact(" ".join(cell_text(x) for x in row))
        if "productnameproductcodepacking" in c and "goodsvalue" in c and "customername" in c:
            return i
    return None


def _col_map(header_row):
    idx = {}
    for i, c in enumerate(header_row):
        role = _ROLE.get(compact(cell_text(c)))
        if role and role not in idx:
            idx[role] = i
    return idx


def detect(rows):
    hidx = _header_idx(rows)
    if hidx is None:
        return False
    idx = _col_map(rows[hidx])
    return "party_name" in idx and "product_name" in idx and "amount" in idx


def parse_senthil_areawise_columnar(rows):
    detected = {"PRODUCT NAME": "product_name", "PACKING": "pack", "QTY": "qty",
                "FREE QTY": "free_qty", "GOODS VALUE": "amount",
                "CUSTOMER NAME": "party_name", "INVNO": "invoice_number"}
    hidx = _header_idx(rows)
    if hidx is None:
        return [], detected
    idx = _col_map(rows[hidx])
    p_i = idx.get("party_name")
    if p_i is None:
        return [], detected

    def g(cells, role):
        i = idx.get(role)
        return cells[i].strip() if (i is not None and i < len(cells)) else ""

    records = []
    for row in rows[hidx + 1:]:
        cells = [cell_text(x) for x in row]
        party = (cells[p_i].strip() if p_i < len(cells) else "")
        if not party or party.upper() == "CUSTOMER NAME":  # blank cell (subtotal/masthead) or a
            continue                                       # page-break repeat of the header row
        product = g(cells, "product_name")
        up = product.upper()
        if not product or up == "PRODUCT NAME" or up.startswith(_SUBTOTAL_PREFIXES):
            continue
        rec = {
            "party_name": party,
            "product_name": product,
            "qty": g(cells, "qty").replace(",", ""),
            "free_qty": (g(cells, "free_qty") or "0").replace(",", ""),
            "amount": g(cells, "amount").replace(",", ""),
        }
        pack = g(cells, "pack")
        if pack:
            rec["pack"] = pack
        inv = g(cells, "invoice_number")
        if inv:
            rec["invoice_number"] = inv
        records.append(rec)
    return records, detected
