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
_PINCODE_RE = re.compile(r"^\d{6}$")
# Footer / grand-total rows: "KLM LABO   Total :" and "TOTAL :".
_TOTAL_RE = re.compile(r"total\s*:", re.IGNORECASE)


def _g(cells, idx):
    return cells[idx] if idx < len(cells) else ""


def detect(rows):
    head = compact(" ".join(" ".join(cell_text(c) for c in r) for r in rows[:8]))
    return "partynamebarcoodeitemname" in head and "companycustomeritemwisesale" in head


def parse_company_customer_itemwise_banded(rows):
    detected = {
        "Party Name": "party_name",
        "Item Name": "product_name",
        "Pack": "pack",
        "Qty.": "qty",
        "Free": "free_qty",
        "Amount": "amount",
    }

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
