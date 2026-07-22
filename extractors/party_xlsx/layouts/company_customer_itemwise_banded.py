"""
"COMPANY - CUSTOMER - ITEM WISE SALE" — MARG/KLM Excel export (DHRUVI HEALTHCARE
PVT LTD ``KLM LAB HO.xlsx``). A banded party-wise sale where each customer group is
introduced by a *cycle* of three column-0 band lines, then its item lines:

    KLM LABO                                                         <- division band (col0 only)
    1STOP WELLNESS | 1STOP WELLNESS | SHELA | 20 GJ GAN 265405       <- CUSTOMER band (name, name, town, GSTIN)
    380058                                                           <- PINCODE band (col0 == ^\\d{6}$)
      | COS0228 | COSMOQ FACE WASH GEL 100ML | 1 | 18 | 3 | - | 1112.95   <- item (col0 blank, col1 barcode)
      ...
      |        |                             |   |    |   |   | 27859.28   <- amount-only subtotal (dropped)

Header row:  Party Name | Barcoode | Item Name | Pack | Stock | Qty. | Free | Amount | % | % Value

Why a dedicated layout (not ``tabular``): the generic ``records_from_mapped`` carry-down
keeps the LAST non-empty Party-Name cell before each item block. Both the CUSTOMER line
and the PINCODE line populate column 0, so the six-digit PINCODE overwrites the real
customer name and every item row gets party_name = pincode (~84 distinct values ->
false DUPLICATE_ROWS AMBER). This layout walks the band cycle explicitly: item rows
always carry a *blank* column 0, so any column-0-populated row is a band — classified
by content (division / pincode / customer) and the pincode never becomes the party.

Title-gated on the distinctive misspelled "Barcoode" banded header ("Party Name
Barcoode Item Name") together with the "COMPANY - CUSTOMER - ITEM WISE SALE" title, so
it diverts only this exact banded export. Flat columnar files that share the title
(party on every row) lack the banded "Barcoode" header and stay on ``tabular``.

--- RATE-COLUMN VARIANT (TANDON MEDICARE ``klm party wise may.xlsx``) --------------
A second vendor ships the SAME title + banded "Barcoode" header but with a different
column schema and band shape:
  * TWO extra rate columns ``Rate | SRate`` are inserted after Pack (and a ``Dis.``
    column after Amount), so the item columns sit two positions to the right — the
    fixed DHRUVI indices (Stock=4, Qty=5, ...) would read Rate/SRate as Stock/Qty.
  * the Barcode column is EMPTY on every item row (the DHRUVI gate `if not barcode`
    would then drop every item -> 0 rows -> tabular fallback -> party = the address).
  * the band that follows each CUSTOMER is a full ADDRESS line (not a bare 6-digit
    pincode), e.g. "A-1248,OPP.BANK OF BARODA,... DELHI-110096  Contact No. : ...".
For this variant only (detected by an ``SRate``/``Rate`` header column), the parser maps
item columns by the printed HEADER row and treats the CUSTOMER band as the col0 row that
carries a populated cell BEYOND col0 (name printed twice, or a town/GSTIN) — the lone-col0
ADDRESS line then never overwrites the customer. The DHRUVI (no-rate) schema keeps the
original fixed-position / barcode-gate / any-col0-band path byte-for-byte unchanged.
"""
import re

from extractors.party_xlsx.parse_common import cell_text, compact

# Column layout is positional (fixed by the printed report), so index the raw cells
# directly instead of header-mapping — the item rows carry no header text.
_PARTY_NAME = 0
_BARCODE = 1
_ITEM_NAME = 2
_PACK = 3
_STOCK = 4
_QTY = 5
_FREE = 6
_AMOUNT = 7

# Division band (ignored). The report prints exactly one company band, "KLM LABO",
# right below the header; treat any all-caps digit-free single-cell col0 that matches
# the company token as the division band.
_DIV_BAND_RE = re.compile(r"^KLM\s*LAB", re.IGNORECASE)
# Pincode band: a bare-numeric col0 band row (address furniture, never a customer whose name
# always carries letters). 6-digit is the Indian pincode; a few exports print a 5-digit local
# code (DHRUVI "32016" under SIDDHARTH MEDICAL) — that too must never become the party.
_PINCODE_RE = re.compile(r"^\d{5,6}$")
# Footer / grand-total rows: "KLM LABO   Total :" and "TOTAL :".
_TOTAL_RE = re.compile(r"total\s*:", re.IGNORECASE)

# Rate-variant header cell -> record field (compacted header text).
_RATE_HEADER_MAP = {
    "itemname": "product_name",
    "pack": "pack",
    "qty.": "qty",
    "qty": "qty",
    "free": "free_qty",
    "amount": "amount",
}


def _g(cells, idx):
    return cells[idx] if idx is not None and 0 <= idx < len(cells) else ""


def _rate_variant_cols(rows):
    """If this is the RATE-column variant (header carries a Rate/SRate column that the
    DHRUVI schema lacks), locate the header row and return {field: col_index} for the
    item columns. Returns None for the DHRUVI schema so the original path runs verbatim."""
    for raw in rows[:12]:
        if not raw:
            continue
        compact_cells = [compact(cell_text(c)) for c in raw]
        if "itemname" not in compact_cells or "amount" not in compact_cells:
            continue
        if "srate" not in compact_cells and "rate" not in compact_cells:
            return None  # DHRUVI schema -> use the original fixed-position path
        cols = {}
        for i, cc in enumerate(compact_cells):
            field = _RATE_HEADER_MAP.get(cc)
            if field and field not in cols:
                cols[field] = i
        if "product_name" in cols and "amount" in cols:
            return cols
        return None
    return None


def detect(rows):
    head = compact(" ".join(" ".join(cell_text(c) for c in r) for r in rows[:8]))
    # The banded "Party Name | Barcode | Item Name" header — vendors ship it both misspelled
    # ("Barcoode", DHRUVI) and correctly ("Barcode", CHANDUKA). Both are this banded export (the
    # CHANDUKA variant otherwise falls to `tabular` and reads its pincode band as the party). Still
    # double-gated on the "Company - Customer - Item Wise Sale" title, so only that exact report routes here.
    has_banded_header = ("partynamebarcoodeitemname" in head or "partynamebarcodeitemname" in head)
    return has_banded_header and "companycustomeritemwisesale" in head


def _parse_rate_variant(rows, cols):
    """TANDON rate-column schema: header-mapped item columns; a CUSTOMER band is a col0
    row with any populated cell beyond col0; the lone-col0 address line is skipped."""
    records = []
    current_party = ""
    current_loc = ""
    for raw in rows:
        if not raw:
            continue
        cells = [cell_text(c) for c in raw]
        first = _g(cells, _PARTY_NAME)

        if first:
            if _TOTAL_RE.search(first):
                continue
            if _PINCODE_RE.match(first):
                continue
            # CUSTOMER band := col0 row carrying a populated cell beyond col0 (the firm
            # name printed twice, or a town / GSTIN). A lone-col0 band is the division
            # header or the ADDRESS block -> skip, never overwrite the customer.
            if any(c for c in cells[1:]):
                current_party = first
                current_loc = _g(cells, _ITEM_NAME)  # col2 town (may be blank)
            continue

        item_name = _g(cells, cols["product_name"])
        if not item_name:
            continue  # amount-only subtotal (Item Name blank)
        free = _g(cells, cols.get("free_qty"))
        if free == "-":
            free = "0"
        records.append(
            {
                "party_name": current_party,
                "party_location": current_loc,
                "product_name": item_name,
                "pack": _g(cells, cols.get("pack")),
                "qty": _g(cells, cols.get("qty")),
                "free_qty": free,
                "amount": _g(cells, cols.get("amount")),
            }
        )
    return records


def parse_company_customer_itemwise_banded(rows):
    detected = {
        "Party Name": "party_name",
        "Item Name": "product_name",
        "Pack": "pack",
        "Qty.": "qty",
        "Free": "free_qty",
        "Amount": "amount",
    }

    cols = _rate_variant_cols(rows)
    if cols is not None:
        return _parse_rate_variant(rows, cols), detected

    # ---- DHRUVI schema: ORIGINAL logic, unchanged -----------------------------
    records = []
    current_party = ""
    current_loc = ""
    for raw in rows:
        if not raw:
            continue
        cells = [cell_text(c) for c in raw]
        first = _g(cells, _PARTY_NAME)
        barcode = _g(cells, _BARCODE)

        # ---- band rows: any row whose column 0 is populated -------------------
        # Item rows always carry a blank column 0, so a non-empty col0 is a band
        # (division / pincode / customer) or a total footer.
        if first:
            if _TOTAL_RE.search(first):          # "KLM LABO Total :" / "TOTAL :"
                continue
            if _DIV_BAND_RE.match(first) and not barcode:   # division band -> ignore
                continue
            if _PINCODE_RE.match(first):         # six-digit pincode band -> ignore
                continue
            # CUSTOMER band: col0 = firm name (col1 duplicates it or is blank),
            # col2 = town, col3 = GSTIN. Set the carry-down identity.
            current_party = first
            current_loc = _g(cells, _ITEM_NAME)
            continue

        # ---- non-band rows: item line or amount-only subtotal -----------------
        if not barcode:
            # amount-only subtotal (col1..col6 blank, only Amount filled) -> drop
            continue

        free = _g(cells, _FREE)
        if free == "-":
            free = "0"
        records.append(
            {
                "party_name": current_party,
                "party_location": current_loc,
                "product_name": _g(cells, _ITEM_NAME),
                "pack": _g(cells, _PACK),
                "qty": _g(cells, _QTY),
                "free_qty": free,
                "amount": _g(cells, _AMOUNT),
            }
        )

    return records, detected
