"""KLM/Marg "Company / Customer / Item / Monthwise Sales Report" — banded QUANTITY
register (PARAS DISTRIBUTORS ``KLM SALES RAGISTAR MAY-26.pdf.xls``).

A monthwise SALES QUANTITY register, grouped Company -> Customer -> Item. Column 0
carries every band line; item rows put the item name in col0, the pack in col3, the
twelve month-quantity columns in cols 4..18 (with blank spacer cols interspersed),
the period Total quantity in col19 and the Average in col20::

    Item Name | | | Pack | APR | | MAY | JUN | | JUL | AUG | SEP | | OCT | ... | Total | Average
    KLM -  COSMO                                              <- COMPANY band (col0 only, no comma-city, no pack)
    ASH24 - ASHIRVAD MEDICAL STORE, AHMEDABAD                 <- CUSTOMER band: "<CODE> - <NAME>, <CITY>"
    EKRAN 30 SILICON SUN GEL | | | 30GM | 0 | | 4 | 0 | ... | 4 | 4   <- ITEM row (col0 item, col3 pack, col19 Total)
    Total (Qty.) of  ASHIRVAD MEDICAL STORE :   | | 4 | ... | 4 | 4    <- customer subtotal (dropped)
    ...
    Total of  KLM :          | | 55720.37 | ... | 55720.37            <- company subtotal (TAXABLE AMOUNT, dropped)
    GRAND TOTAL :            | | 55720.37 | ... | 55720.37            <- grand total (dropped)

QTY-ONLY report: the item-level month columns and the Total column are QUANTITIES
(small integers). The Company / Grand-Total footer rows print a TAXABLE AMOUNT
(``Note : Amount = Taxable Amount.``), NOT a quantity — those footers are dropped, so
the amount never contaminates a qty column. There is no per-item value/rate/amount
column in this report, so no amount field is emitted.

The Total column (col19) is the sum of the twelve month quantities = the item's sales
quantity for the report period; it is mapped to ``qty``. qty is read straight from the
printed Total column — never derived from any value/amount column (there is none).

Band walk (explicit, like company_customer_itemwise_banded): item rows always carry a
non-empty pack (col3). A col0-populated row is a band: a COMPANY band (starts "KLM",
no comma-city, no pack), a CUSTOMER band ("<CODE> - <NAME>, <CITY>"), or a Total/GRAND
footer. Only item rows emit records; the customer band is the carry-down party.

Gate: the compact title run "companycustomeritemmonthwisesalesreport" (compact() strips
'/' and spaces) — unique to this export; no other corpus file carries
"monthwisesalesreport".
"""
import re

from extractors.party_xlsx.parse_common import cell_text, compact

_GATE = "companycustomeritemmonthwisesalesreport"

# Positional columns (fixed by the printed report).
_ITEM = 0
_PACK = 3
_TOTAL = 19

# CUSTOMER band: "<CODE> - <NAME>, <CITY>" — a code, a spaced hyphen, then a
# comma-separated trade name + town. The COMPANY band ("KLM -  COSMO") has no
# trailing comma-city, so it never matches this.
_CUST_RE = re.compile(r"^\S.*\s-\s.+,\s*[A-Za-z]")
_COMPANY_RE = re.compile(r"^KLM\b")
_TOTAL_RE = re.compile(r"^(total\b|grand\s*total)", re.IGNORECASE)
# Header / page-furniture noise lines that also land in col0.
_NOISE_RE = re.compile(
    r"^(item\s*name$|year\s*:|company\s*/\s*customer|nid\d|page\s+\d)", re.IGNORECASE
)


def _g(cells, idx):
    return cells[idx] if idx < len(cells) else ""


def _compact_head(rows):
    return compact(" ".join(" ".join(cell_text(c) for c in r) for r in rows[:12]))


def detect(rows):
    return _GATE in _compact_head(rows)


def _split_customer(band):
    """'311D105 - DEEPAK MEDICAL & PROVI.STORES, AHMEDABAD' -> (name, city)."""
    body = band.split(" - ", 1)[1] if " - " in band else band
    if "," in body:
        name, city = body.rsplit(",", 1)
        return name.strip(), city.strip()
    return body.strip(), ""


def parse_company_customer_monthwise_sales(rows):
    detected = {
        "Item Name": "product_name",
        "Pack": "pack",
        "Total": "qty",
    }

    records = []
    current_party = ""
    current_city = ""
    for raw in rows:
        if not raw:
            continue
        cells = [cell_text(c) for c in raw]
        first = _g(cells, _ITEM).strip()
        if not first:
            continue

        pack = _g(cells, _PACK).strip()

        # Item row: non-empty pack column, and col0 is not a customer band.
        if pack and not _CUST_RE.match(first):
            total = _g(cells, _TOTAL).strip()
            if not total or not re.match(r"^-?[\d,]*\.?\d+$", total):
                continue
            records.append(
                {
                    "party_name": current_party,
                    "party_location": current_city,
                    "product_name": first,
                    "pack": pack,
                    "qty": total.replace(",", ""),
                }
            )
            continue

        # Band / footer rows (non-empty col0, empty pack).
        if _TOTAL_RE.match(first) or _NOISE_RE.match(first):
            continue
        if _CUST_RE.match(first):
            current_party, current_city = _split_customer(first)
            continue
        # COMPANY band ("KLM -  COSMO") or any other col0-only band -> ignore.
        # (COMPANY_RE kept for clarity; unmatched col0-only lines are also skipped.)
        continue

    return records, detected
