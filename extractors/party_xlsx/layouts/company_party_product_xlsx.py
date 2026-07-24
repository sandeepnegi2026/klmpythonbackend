"""KLM "Company Party Wise Product Sale" 3-level banded export (GARG DISTRIBUTOR).

Structure::

    Company Party Wise Product S...                       <- title
    COMPANY / PARTY / PRODUCT | QTY | FREE | RPL | AMT | DISC | TAX |
    NET AMT | FREE AMT | SALE RATE                        <- header
    KLM COSMO                                             <- company band (starts "KLM")
    ANJALI MEDICAL HALL                                   <- party band (all numerics blank)
    HERPIVAL-500 TAB | 6 | 0 | 0 | 625.02 | ...           <- product line
    PARTY TOTAL :    | ...                                <- subtotal (skip)

The generic ``tabular`` reader maps the numeric columns but the single
COMPANY/PARTY/PRODUCT column can only bind to product_name, so party_name is
never extracted (RED MISSING_REQUIRED_FIELD). This parser carries the party
band down onto each product line and skips the "KLM ..." company bands.

A sales-RETURN line prints with QTY/AMT blank and only a negative NET AMT
(e.g. -107.43); its amount falls back to NET AMT so the return is not lost.
"""
import re

from extractors.party_xlsx.parse_common import cell_text, compact

_HDR = ("qty", "free", "rpl", "amt", "disc", "tax", "net amt", "free amt", "sale rate")


def _header_idx(rows):
    for idx, row in enumerate(rows[:12]):
        cells = [cell_text(c).strip().lower() for c in row]
        if "company / party / product" in cells and "rpl" in cells and "net amt" in cells:
            return idx
    return None


def detect(rows):
    title = compact(" ".join(" ".join(cell_text(c) for c in r) for r in rows[:4]))
    if "companypartywiseproduct" not in title:
        return False
    return _header_idx(rows) is not None


def parse_company_party_product_xlsx(rows):
    header_idx = _header_idx(rows)
    if header_idx is None:
        return [], {}
    header = [cell_text(c).strip().lower() for c in rows[header_idx]]
    col = {}
    for j, h in enumerate(header):
        if h == "company / party / product":
            col["name"] = j
        elif h == "qty":
            col["qty"] = j
        elif h == "free":
            col["free_qty"] = j
        elif h == "amt":
            col["amount"] = j
        elif h == "net amt":
            col["net"] = j
        elif h == "sale rate":
            col["rate"] = j

    def _val(cells, key):
        i = col.get(key)
        return cells[i].strip() if (i is not None and i < len(cells)) else ""

    records = []
    party = ""
    for raw in rows[header_idx + 1:]:
        cells = [cell_text(c) for c in raw]
        name = _val(cells, "name")
        if not name:
            continue
        if "total" in name.lower():
            continue
        qty, amt, net = _val(cells, "qty"), _val(cells, "amount"), _val(cells, "net")
        if not qty and not amt and not net:
            # band row: "KLM <DIV>" = company (skip), anything else = party
            if not re.match(r"^KLM\b", name, re.I):
                party = name
            continue
        if not party:
            continue
        rec = {
            "party_name": party,
            "product_name": name,
            "qty": qty or "0",
            "free_qty": _val(cells, "free_qty") or "0",
            "amount": amt or net,     # return lines carry only a negative NET AMT
        }
        rate = _val(cells, "rate")
        if rate:
            rec["rate"] = rate
        records.append(rec)

    detected = {"COMPANY / PARTY / PRODUCT": "product_name", "QTY": "qty",
                "FREE": "free_qty", "AMT": "amount", "SALE RATE": "rate"}
    return records, detected
