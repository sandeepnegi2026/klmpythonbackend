"""
Itemwise Sales Details — product-banded report with a party *column*.

A family of ERP exports ("Itemwise Sales Details", e.g. JEEVANREKHA / ARIHANT /
VIJAYPD) inverts the usual party-wise banding: the **product** is the band header
and each sale line underneath names its customer in a ``Party Code & Name`` column:

    Bill No | BillDt | SM | Party Code & Name | Batch No | Rate | Qnty | Free | ... | Value | ExpDt
    260   KLM PEDIA                                       <- division band
    5951  DESOSOFT CREAM 10GM                             <- product band (item code + name)
    26001764 14-05-26 87 23970 DHANVANTARI CHEMIST BJ601 107.14 5 ...   <- sale line
                              BHANDUP                     <- party city (carried onto the line)

The generic ``tabular`` parser anchors on the title/banner row (it has 3 weak header
matches) instead of the real ``Bill No … Party Code & Name … Qnty`` row, so the party
never maps (-> MISSING_REQUIRED_FIELD:party_name). This layout finds the real header,
carries the current product band down, and reads the party from each sale line.

Column positions are anchored on the **BillDt date cell** rather than fixed indices,
because two style variants exist: one where the line starts at column 0 (JEEVANREKHA /
ARIHANT) and one with a leading blank column that shifts everything right (VIJAYPD).
Relative to the bill date these offsets hold for both: party code = date+2, party name
= date+3, batch = date+4, rate = date+5, qty = date+6. The amount is read from the
header's ``Value`` column (right-aligned in both variants).
"""
import re

from core.header_match import normalize

from extractors.party_xlsx.parse_common import cell_text, is_numeric_qty, is_subtotal, looks_like_date

_INT_RE = re.compile(r"^\d{1,9}$")
# A header row for this layout always pairs the party-code column with the Marg-style
# "Qnty" quantity header (or a "Bill No" document column) — specific enough that no
# other Excel layout is diverted here.
_PARTY_CODE_HDR = "party code"
# Some exports of this report omit the column-header row entirely, going straight from
# the "Itemwise Sales Details" banner to the division/product bands and sale lines. The
# banner is the distinctive signal in that case (the data is still date-anchorable).
_TITLE = "itemwise sales details"


def _clean(raw):
    """Row cells as text, with pandas ``NaT`` placeholders blanked (some .xls exports
    leave a trailing all-NaT column that would otherwise leak the string 'NaT')."""
    return ["" if cell_text(c) in ("NaT", "nan") else cell_text(c) for c in raw]


def _is_name(text):
    return bool(re.search(r"[A-Za-z]{3,}", text)) and not _INT_RE.match(text)


def detect_header_idx(rows):
    for idx, row in enumerate(rows[:15]):
        joined = normalize(" ".join(cell_text(c) for c in row))
        if _PARTY_CODE_HDR in joined and ("qnty" in joined or "bill no" in joined or "billno" in joined):
            return idx
    return None


def _title_idx(rows):
    for idx, row in enumerate(rows[:8]):
        if _TITLE in normalize(" ".join(cell_text(c) for c in row)):
            return idx
    return None


def detect(rows):
    """True for the Itemwise Sales Details layout — with or without a column header."""
    return detect_header_idx(rows) is not None or _title_idx(rows) is not None


def parse_itemwise_party_column(rows):
    header_idx = detect_header_idx(rows)
    value_idx = None
    if header_idx is not None:
        for idx, cell in enumerate(rows[header_idx]):
            if normalize(cell) == "value":
                value_idx = idx
                break
        start = header_idx + 1
    else:
        # header-less variant: anchor below the "Itemwise Sales Details" banner.
        title = _title_idx(rows)
        if title is None:
            return [], {}
        start = title + 1

    records = []
    current_product = ""
    for raw in rows[start:]:
        cells = _clean(raw)
        if not any(cells):
            continue
        low = " ".join(cells).lower()
        if "item total" in low or "grand total" in low or is_subtotal(cells[0]):
            continue

        # bill date = first date in the leading cells -> this is a sale line
        date_i = next((i for i, c in enumerate(cells[:5]) if looks_like_date(c)), None)
        if date_i is not None and date_i + 3 < len(cells):
            name = cells[date_i + 3]
            code = cells[date_i + 2]
            if not _is_name(name):
                # tolerate a one-cell drift in where the party name lands
                window = [j for j in range(date_i + 2, min(len(cells), date_i + 5)) if _is_name(cells[j])]
                if not window:
                    continue
                name = cells[window[0]]
                code = cells[window[0] - 1] if window[0] > 0 else ""
            if not current_product:
                continue
            record = {
                "party_name": name,
                "party_code": code,
                "product_name": current_product,
                "invoice_number": cells[date_i - 1] if date_i >= 1 else "",
                "invoice_date": cells[date_i],
                "batch_no": cells[date_i + 4] if date_i + 4 < len(cells) else "",
                "rate": cells[date_i + 5] if date_i + 5 < len(cells) else "",
                "qty": cells[date_i + 6] if date_i + 6 < len(cells) else "",
            }
            if value_idx is not None and value_idx < len(cells):
                record["amount"] = cells[value_idx]
            else:
                # header-less variant: the line value is the last numeric cell sitting
                # before the trailing expiry-date column.
                for c in reversed(cells[date_i + 7:]):
                    if c and not looks_like_date(c) and is_numeric_qty(c):
                        record["amount"] = c
                        break
            record.pop("party_code")
            records.append(record)
            continue

        # no date -> a band row or a party-city continuation
        band_name = None
        for j in range(len(cells) - 1):
            if _INT_RE.match(cells[j]) and _is_name(cells[j + 1]):
                band_name = cells[j + 1]
                break
        if band_name is not None:
            # a division band (e.g. "260 KLM PEDIA") is always immediately followed by
            # its first product band before any sale line, so storing it as the current
            # product is harmless — it is overwritten before it can reach a row.
            current_product = band_name
            continue

        names = [c for c in cells if _is_name(c)]
        if len(names) == 1 and records:
            records[-1].setdefault("party_location", names[0].lstrip("*").strip())

    detected = {
        "Party Code & Name": "party_name",
        "Bill No": "invoice_number",
        "BillDt": "invoice_date",
        "Qnty": "qty",
        "Free": "free_qty",
        "Rate": "rate",
        "Value": "amount",
        "Batch No": "batch_no",
        "ExpDt": "expiry",
    }
    return records, detected
