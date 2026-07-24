"""KLM "Company Party Wise Product Sale" — FLAT variant (NEW JAGDAMBA AGENCY).

A sibling of company_party_product_xlsx (GARG) but with only QTY / FREE / AMT
columns (no RPL / NET AMT / DISC / TAX). Structure::

    Company Party Wise Product Sale Report ...            <- title
    COMPANY / PARTY / PRODUCT | QTY | FREE | AMT          <- header
    KLM COAMO DIVI                                        <- company band (starts "KLM")
    .OM MEDICAL HALL                                      <- party band
    IMXIA PRO SERUM | 1 | 0 | 945.76                      <- product line
    NIOFINE TAB                                           <- ZERO-VALUE product (blank qty/amt)

The single COMPANY/PARTY/PRODUCT column mixes three record types on blank-numeric
rows, so the GARG parser's "blank numerics => party band" rule is unsafe here: ~16
product lines print with blank QTY/AMT and would be mistaken for parties, corrupting
attribution. Instead a blank-numeric row is a PARTY only when it (a) immediately
follows a company/total boundary, or (b) carries a party-name keyword; otherwise it
is a zero-value product line kept under the current party. sum(AMT) reconciles EXACTLY
to the printed GRAND TOTAL.
"""
import re

from extractors.party_xlsx.parse_common import cell_text, compact

_PARTY_TOK = re.compile(
    r"\b(MEDICAL|MEDICALS|MEDICO|MEDICOSE|MEDICARE|MEDICINE|MEDICINES|MEDICURE|MEDCALS|"
    r"MEDISALES|PHARMA|PHARMACEUTICAL|PHARMACEUTICALS|PHARMACY|DISTRIBUTOR|DISTRIBUTORS|"
    r"AGENCY|AGENCIES|STORE|STORES|HALL|DRUG|DRUGS|CLINIC|ENTERPRISE|ENTERPRISES|HOUSE|"
    r"TRADERS|SURGICAL|CHEMIST|HEALTH|CARE|SALES|MART|CENTRE|CENTER|HOSPITAL|BHANDAR)\b")


def _looks_party(t):
    u = t.upper()
    return bool(_PARTY_TOK.search(u)) or u.startswith(("DR ", "DR.", "M/S", "."))


def _header_idx(rows):
    for idx, row in enumerate(rows[:12]):
        cells = [cell_text(c).strip().lower() for c in row]
        if "company / party / product" in cells and "amt" in cells and "net amt" not in cells:
            return idx
    return None


def detect(rows):
    title = compact(" ".join(" ".join(cell_text(c) for c in r) for r in rows[:4]))
    if "companypartywiseproduct" not in title:
        return False
    return _header_idx(rows) is not None


def parse_company_party_product_flat_xlsx(rows):
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

    def _val(cells, key):
        i = col.get(key)
        return cells[i].strip() if (i is not None and i < len(cells)) else ""

    records = []
    party = ""
    boundary = True
    for raw in rows[header_idx + 1:]:
        cells = [cell_text(c) for c in raw]
        name = _val(cells, "name")
        if not name:
            continue
        low = name.lower()
        if low.startswith("grand total"):
            continue
        if low.startswith(("company total", "party total")):
            boundary = True
            continue
        qty = _val(cells, "qty")
        free = _val(cells, "free_qty")
        amt = _val(cells, "amount")
        if qty or free or amt:                       # product line with values
            records.append({
                "party_name": party, "product_name": name,
                "qty": qty or "0", "free_qty": free or "0", "amount": amt or "0",
            })
            boundary = False
            continue
        # blank-numeric row: company band / party band / zero-value product
        if re.match(r"^KLM\b", name, re.I):
            party = ""
            boundary = True
        elif boundary or _looks_party(name):
            party = name
            boundary = False
        else:
            records.append({"party_name": party, "product_name": name,
                            "qty": "0", "free_qty": "0", "amount": "0"})

    detected = {"COMPANY / PARTY / PRODUCT": "product_name", "QTY": "qty",
                "FREE": "free_qty", "AMT": "amount"}
    return records, detected
