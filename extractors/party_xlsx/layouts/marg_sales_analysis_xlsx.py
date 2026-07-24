"""
MARG "Sales Analysis" party report — XLSX variant (VENUS PHARMA `KLM MAY PARTY.XLSX`).

The report is 3-level banded:

    Manufacturer band   "KLM LABORATORIES -COSMOCOR (XA0001)"          <- division, ignored
    Customer band       "AARTI MEDICAL STORE   SET-6 - GANDHINAGAR (563)"  <- party
    item line           "NIOSALIC LOTION 50ML (XA0193) | 1 | 0 | 128.57 ..."

Header row (title "Sales Analysis Date : …") maps to columns:

    col3  = customer band text (carried onto every product line)
    col1  = manufacturer band text (division; ignored)
    col4  = Item name  "PRODUCT (code)"   (duplicated in col5 across merged cells)
    col6  = Qty
    col7  = Free
    col8  = Value #    (= Qty * Rate, sales value -> amount)
    col9..col13 = per-line running Total Qty / Total Free / Total Value  (ignored)

Crucially the customer band is emitted into col3 of EVERY product line, so the party is
read directly per row — no fragile band-carry state is needed for the party. Band-only
rows (manufacturer / customer heading rows) have the item columns blank and are skipped;
per-customer subtotal rows and the printed "Grand Total 2310 306 440114.22" have the Item
cell blank (or literally "Grand Total") and are skipped too.

Customer band shape:  "<NAME> [SET-n] - <CITY> (<code>)"  ->  party_name + party_location.
This layout is title-gated (see detect) on the "Sales Analysis" + "Item Qty Free Value"
+ Manufacturer/Customer band signature, so it diverts only this specific MARG export.
"""
import re

from core.header_match import normalize

from extractors.party_xlsx.parse_common import cell_text, is_numeric_qty

# Column layout is fixed for this MARG "Sales Analysis" export.
COL_DIV = 1        # manufacturer band on product lines (division, ignored)
COL_PARTY = 3      # customer band carried onto every product line
COL_ITEM = 4       # item name "PRODUCT (code)"
COL_QTY = 6
COL_FREE = 7
COL_VALUE = 8      # Value #  = Qty*Rate (sales value)

# "<NAME> [SET-n] - <CITY> (<code>)". Non-greedy name, optional trailing " (code)".
_PARTY_RE = re.compile(
    r"^(?P<name>.*?)\s*(?:\bSET-\d+\b)?\s*-\s*(?P<city>[^-(]*?)\s*\((?P<code>[^)]*)\)\s*$"
)
# Trailing " (code)" on an item name — dropped so product-master enrichment gets a clean name.
_CODE_SUFFIX_RE = re.compile(r"\s*\([^)]*\)\s*$")
# Total / grand-total labels that can sit in the Item cell.
_TOTAL_RE = re.compile(r"^\s*(?:grand\s+)?total\b", re.IGNORECASE)


def _ws(text):
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def detect(rows):
    head = normalize(
        " ".join(" ".join(cell_text(c) for c in r) for r in rows[:12])
    ).replace(" ", "")
    return (
        "salesanalysis" in head
        and "itemqtyfreevalue" in head
        and "manufacturer" in head
        and "customer" in head
    )


def _split_party(text):
    """"<NAME> [SET-n] - <CITY> (<code>)" -> (party_name, party_location)."""
    raw = _ws(text)
    m = _PARTY_RE.match(raw)
    if m:
        name = _ws(m.group("name"))
        city = _ws(m.group("city"))
        if name:
            return name, city
    # Fallback: drop a trailing "(code)" and keep the rest as the name.
    return _ws(_CODE_SUFFIX_RE.sub("", raw)), ""


def parse_marg_sales_analysis_xlsx(rows):
    records = []
    detected = {
        "Customer": "party_name",
        "Item": "product_name",
        "Qty": "qty",
        "Free": "free_qty",
        "Value #": "amount",
    }

    for raw in rows:
        if not raw:
            continue
        item = cell_text(raw[COL_ITEM]) if len(raw) > COL_ITEM else ""
        if not item or _TOTAL_RE.match(item):
            # Band-only row, per-customer subtotal, Grand Total, header or footer.
            continue
        # A real product line carries a numeric Qty or Value.
        qty_cell = cell_text(raw[COL_QTY]) if len(raw) > COL_QTY else ""
        val_cell = cell_text(raw[COL_VALUE]) if len(raw) > COL_VALUE else ""
        if not (is_numeric_qty(qty_cell) or is_numeric_qty(val_cell)):
            continue
        party_raw = cell_text(raw[COL_PARTY]) if len(raw) > COL_PARTY else ""
        if not party_raw:
            continue

        party_name, party_location = _split_party(party_raw)
        product = _ws(_CODE_SUFFIX_RE.sub("", item))
        record = {
            "party_name": party_name,
            "product_name": product,
            "qty": qty_cell,
            "free_qty": cell_text(raw[COL_FREE]) if len(raw) > COL_FREE else "",
            "amount": val_cell,
        }
        if party_location:
            record["party_location"] = party_location
        records.append(record)

    return records, detected
