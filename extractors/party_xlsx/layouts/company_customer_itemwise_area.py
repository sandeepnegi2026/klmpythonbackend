"""
"COMPANY-CUSTOMER-ITEM WISE SALE" — MARG Excel export, PONDY variant (YOGIRAM
DISTRIBUTORS PVT LTD ``__PONDY - *.xlsx``). A banded party-wise sale where each
customer group is introduced by a column-0 ``[ <code> ] <NAME>`` band row, then
its item lines:

    Party Name | Item Name | Area | Pack | (blank) | Qty. | Free | Amount   <- header
    00 | 00 | 00 | 00 | 00 | 00 | 00 | 00                                    <- junk row (dropped)
    [ 1654 ] ABIRAMY MEDICALS | [ 1654 ] ABIRAMY MEDICALS | THIRUKKANUR | .. <- CUSTOMER band
    320894 | NIOSALIC 6 LOTION 50ML | | 50 ML | | 1 | - | 135.71             <- item line
      | | | | | | Total : | 135.71                                          <- per-party subtotal (dropped)
    ...
    TOTAL : | | | | | | | 158451.51                                         <- grand total footer (dropped)

This is the NO-"Barcoode" sibling of ``company_customer_itemwise_banded``. Here the
party sits in a ``[ <code> ] <NAME>`` band (its Area in col2) and each ITEM line
carries a numeric raw item CODE in column 0 (not a blank col0 + barcode col1). The
generic ``tabular`` carry-down keeps the LAST non-empty Party-Name cell, so every
item row would inherit the band's raw "[ <code> ] <NAME>" text as party_name; this
layout walks the bands explicitly and strips the "[ <code> ] " prefix.

Title-gated on the "COMPANY-CUSTOMER-ITEM WISE SALE" title + the exact
"Party Name | Item Name | Area" header run WITHOUT the misspelled "Barcoode" token
(which routes the banded sibling) plus a "[ <code> ] <NAME>" band, so it diverts
only this exact export; flat-columnar twins of the same title stay on ``tabular``.
"""
import re

from extractors.party_xlsx.parse_common import cell_text, compact

# Column layout is positional (fixed by the printed report), so index the raw cells
# directly instead of header-mapping — the item rows carry no header text.
_ITEM_CODE = 0
_ITEM_NAME = 1
_AREA = 2
_PACK = 3
_QTY = 5
_FREE = 6
_AMOUNT = 7

# Party band: "[ <code> ] <NAME>" in column 0.
_PARTY_BAND_RE = re.compile(r"^\[\s*\d+\s*\]\s+(\S.*)$")
# An ITEM line carries a numeric raw item code in column 0. The report prints one
# all-'00' junk row right under the header; a bare '0'/'00' code is never a real
# item, so require at least one non-zero digit to admit an item line.
_ITEM_CODE_RE = re.compile(r"^0*[1-9]\d*$")
# Footer / subtotal rows: per-party "Total :" (col6) and grand "TOTAL :" (col0).
_TOTAL_RE = re.compile(r"total\s*:", re.IGNORECASE)


def _g(cells, idx):
    return cells[idx] if idx < len(cells) else ""


def detect(rows):
    head = compact(" ".join(" ".join(cell_text(c) for c in r) for r in rows[:10]))
    if "companycustomeritemwisesale" not in head:
        return False
    if "partynameitemnamearea" not in head:
        return False
    if "barcoode" in head:
        return False
    return any(_PARTY_BAND_RE.match(cell_text(r[0]) if r else "") for r in rows[:40])


def parse_company_customer_itemwise_area(rows):
    detected = {
        "Party Name": "party_name",
        "Item Name": "product_name",
        "Area": "party_location",
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
        first = _g(cells, _ITEM_CODE)

        # ---- band / footer rows -------------------------------------------------
        band = _PARTY_BAND_RE.match(first)
        if band:
            # CUSTOMER band: col0/col1 = "[ code ] name", col2 = Area. Set carry-down.
            current_party = band.group(1).strip()
            current_loc = _g(cells, _AREA)
            continue
        # Grand-total footer "TOTAL :" sits in col0; per-party "Total :" sits in col6.
        if _TOTAL_RE.search(first) or _TOTAL_RE.search(_g(cells, _FREE)):
            continue

        # ---- item lines: numeric raw item code in column 0 ----------------------
        if not _ITEM_CODE_RE.match(first):
            # all-'00' junk row (col0 == "00") and any other non-item noise -> drop.
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
