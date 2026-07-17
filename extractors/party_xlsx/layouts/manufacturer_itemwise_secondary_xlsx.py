"""
"Manufacturer Wise Item Wise (Secondary Sales)" — SHRI JAYANTHI PHARMA PVT LTD Excel
export (an XLSX saved with a ``.xls`` extension; ``Klm Areawise ... .xls``). A 3-level
banded party-wise sales register:

    SHRI JAYANTHI PHARMA PVT LTD                                    <- masthead (row 0)
    Manufacturer Wise Item Wise (Secondary Sales) From 01/06/26 ..  <- title  (row 1)
    Inv No | Date | Batch | Q | F | R | Rate | Val | Code | Name | Place | City | ...
    (only col-9 populated) KLM LABORATORIES PVT LTD (PHARMA)  (541) <- MANUFACTURER band -> division
    (only col-9 populated) EBERFINE CREAM 15GM(54104)              <- PRODUCT band
    JA35262 09/06/2026 BM514 1 0 0 153.57 153.57 6434 POOJA MEDICALS KAKKALUR, ...
    ...                                                             <- invoice sale lines
    (col1) Total  ...  5 0 0  767.85                                <- per-product subtotal -> skip
    Grand Total ...  14394.49                                      <- per-manufacturer total -> skip
    Report Total ... 161742.66                                     <- grand total -> skip

WHY A NEW LAYOUT: the single-letter headers Q/F/R and "Val" do not map through the shared
``map_headers`` synonym set (and must NOT be added there — the no-short-fuzzy-synonym rule),
so the generic ``tabular`` reader binds nothing: party_name/product_name/qty/amount all empty
(bare "Name" -> vendor_name), and the band rows (only col-9 populated) are dropped. This
reader binds every column by its FIXED header index instead.

COLUMN MAP (by header index on the "Inv No | Date | Batch | Q | F | R | Rate | Val | Code |
Name | Place | City | ..." header row):
    Inv No[0]  -> invoice_number     Date[1]  -> invoice_date
    Batch[2]   -> batch_no           Q[3]     -> qty
    F[4]       -> free_qty           R[5]     -> (return qty; 0 in the sample — DROPPED,
                                                  not a party canonical field)
    Rate[6]    -> rate               Val[7]   -> amount
    Name[9]    -> party_name         Place[10]-> party_location
Product/division come from the band rows carried down.

BANDS: a band row has only col-9 populated. If its text contains "KLM LABORATORIES" (or ends
in a 3-digit "(NNN)" manufacturer code) it is a MANUFACTURER band -> division. Otherwise it is
a PRODUCT band -> product_name (the trailing "(54xxx)" 5-digit item code is stripped).

RECONCILE: qty sum == per-product Total / per-mfr Grand Total / Report Total; sample:
qty 895, amount 161,742.66 == printed Report Total (per-mfr Grand Totals sum to the same).
"""
import re

from extractors.party_xlsx.parse_common import cell_text, compact

# Header row: the compact of the 17 short cells carries these unique tokens.
_HDR_TOKENS = ("invno", "batch", "rate", "val", "sman")

# A trailing item / manufacturer code in parentheses at the very end of a band cell:
# products carry a 5-digit "(54104)" item code, manufacturers a 3-digit "(541)" code.
_TRAIL_CODE_RE = re.compile(r"\s*\((\d{3,6})\)\s*$")


def _ws(text):
    return re.sub(r"\s+", " ", str(text).replace("\xa0", " ")).strip()


def _header_idx(rows):
    for i, row in enumerate(rows[:30]):
        comp = compact(" ".join(cell_text(c) for c in row))
        if all(tok in comp for tok in _HDR_TOKENS):
            return i
    return None


def detect(rows):
    head = compact(" ".join(" ".join(cell_text(c) for c in r) for r in rows[:8]))
    # Title token — "Manufacturer Wise Item Wise (Secondary Sales)" compacts to this.
    # Unique to this export; no other party_xlsx gate references it.
    if "manufacturerwiseitemwise" not in head:
        return False
    return _header_idx(rows) is not None


def _is_band(cells):
    """A band row has text only in col-9 (Name) — every other cell blank."""
    populated = [j for j, c in enumerate(cells) if c]
    return populated == [9]


def _split_product(text):
    """Strip a trailing '(54xxx)' item code from a product band, returning the name."""
    m = _TRAIL_CODE_RE.search(text)
    if m:
        return text[: m.start()].strip()
    return text.strip()


def parse_manufacturer_itemwise_secondary_xlsx(rows):
    detected = {
        "Inv No": "invoice_number", "Date": "invoice_date", "Batch": "batch_no",
        "Q": "qty", "F": "free_qty", "Rate": "rate",
        "Val": "amount", "Name": "party_name", "Place": "party_location",
    }
    hidx = _header_idx(rows)
    if hidx is None:
        return [], detected

    records = []
    division = ""
    product = ""
    for raw in rows[hidx + 1:]:
        if not raw:
            continue
        cells = [cell_text(c) for c in raw]
        col0 = cells[0].strip() if cells else ""

        # Per-product ("Total" in col1), per-mfr ("Grand Total") and grand ("Report Total")
        # subtotal rows -> skip.
        col1 = cells[1].strip() if len(cells) > 1 else ""
        if col1 == "Total" or col0 in ("Grand", "Report"):
            continue

        if _is_band(cells):
            band = _ws(cells[9])
            if not band:
                continue
            if "KLM LABORATORIES" in band.upper():
                # Manufacturer band -> division (strip the "(541)" mfr code for a clean name).
                division = _TRAIL_CODE_RE.sub("", band).strip()
            else:
                product = _split_product(band)
            continue

        # A sale line is anchored on a non-empty Inv No (col 0).
        if not col0:
            continue

        rec = {
            "invoice_number": col0,
            "invoice_date": cells[1] if len(cells) > 1 else "",
            "batch_no": cells[2] if len(cells) > 2 else "",
            "qty": (cells[3] if len(cells) > 3 else "0").replace(",", ""),
            "free_qty": (cells[4] if len(cells) > 4 else "0").replace(",", ""),
            "rate": (cells[6] if len(cells) > 6 else "0").replace(",", ""),
            "amount": (cells[7] if len(cells) > 7 else "0").replace(",", ""),
            "party_name": _ws(cells[9]) if len(cells) > 9 else "",
            "product_name": product,
        }
        loc = _ws(cells[10]).rstrip(",") if len(cells) > 10 else ""
        if loc:
            rec["party_location"] = loc
        if division:
            rec["division"] = division
        records.append(rec)

    return records, detected
