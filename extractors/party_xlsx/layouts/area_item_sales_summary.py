"""
"AREA / ITEM WISE SALES SUMMARY" — the XLS twin of the party_pdf layout of the same
name (AGARTALA PHARMA LLP / KLM export). The whole report is space-padded text crammed
one line per single cell:

    AREA / ITEM WISE SALES SUMMARY FROM 01-05-2026-31-05-2026
    D E S C R I P T I O N            QTY.    FREE    RATE    AMOUNT
    -ABANTIKA MEDICAL HALL KASHIPUR                       <- party band (leading '-')
    COSMOQ-OC MOISTURI 60GM      2      -     356.25    712.50   <- product line
    4        0            1002.82                        <- per-party subtotal -> skip

Distinct from ``party_item_summary`` (title "PARTY / ITEM WISE SALES SUMMARY", bare-name
bands) two ways: the title is "AREA / ...", and every party band carries a leading '-'.
It is also the four-numeric-column variant — the 5S/NAVKAR ``area_item_summary`` carries a
trailing "( % )" discount column, guarded out here by requiring no "%" in the header.
Line-parsing mirrors the accepted party_pdf ``area_item_sales_summary`` byte-for-byte.

MAPPING: party_name = band text (leading '-' stripped); product_name; qty; free_qty
(free, "-" -> 0); rate; amount.
"""
import re

from core.header_match import normalize

from extractors.party_xlsx.parse_common import cell_text, compact

# --- party_name / party_location split -------------------------------------------------
# Each band glues the firm name and its town with a plain space and NO delimiter
# ("ABANTIKA MEDICAL HALL KASHIPUR", "JOY RAM MEDICAL HALL OLD MOTOR STAND"). There is no
# structural separator, but the firm name reliably ENDS with a pharma business-type token
# and the town follows. We split on the LAST such token; the tail (which may be multi-word,
# e.g. "OLD MOTOR STAND") becomes party_location. A compound firm name whose business token
# is followed by a name-continuation word ("MEDICINE POINT", "CURE CORNER", "LIFE LINE") is
# NOT split there, and a band with no recognised token is left whole (party_location "") —
# so the split never corrupts a firm name, it only peels a town when confident.
_BIZ = {
    "MEDICAL", "MEDICALS", "MEDICAL'S", "HALL", "PHARMACY", "PHARMA", "PHARMACEUTICAL",
    "PHARMACEUTICALS", "DRUG", "DRUGS", "DRUGGIST", "DRUGGISTS", "CHEMIST", "CHEMISTS",
    "AGENCY", "AGENCIES", "ENTERPRISE", "ENTERPRISES", "STORE", "STORES", "LIFECARE",
    "SURGICAL", "SURGICALS", "DISTRIBUTOR", "DISTRIBUTORS", "MEDICOSE", "MEDICOS",
    "TRADERS", "CENTRE", "CENTER", "DEPOT", "MEDICINE", "MEDICINES", "MEDICARE",
    "MEDISHOP", "MEDIPOINT", "MEDZONE", "MEDIHUT", "MEDIHUB", "PHARMACO", "REMEDIES",
    "SPECIALITIES", "HEALTHCARE",
}
_CONT = {
    "POINT", "CORNER", "LINE", "PLUS", "CARE", "ZONE", "HUT", "HUB", "SHOP", "HOUSE",
    "WORLD", "MART", "KART", "BAG", "AND", "&", "CO", "CO.", "COMPANY",
}


def _split_band(name):
    """Split "<FIRM NAME> <TOWN>" on the last business-type token. Returns
    (party_name, party_location); party_location is "" when nothing splits confidently."""
    toks = name.split()
    split_at = -1
    for i, tok in enumerate(toks):
        base = tok.strip(".,").upper()
        if base in _BIZ and i + 1 < len(toks) and toks[i + 1].strip(".,").upper() not in _CONT:
            split_at = i          # last valid terminal token wins
    if split_at == -1:
        return name, ""
    return " ".join(toks[: split_at + 1]), " ".join(toks[split_at + 1:])

_NUM = r"[\d,]+\.\d+"                       # rate / amount always carry decimals
_QTY = r"\d[\d,]*(?:\.\d+)?"                # qty: integer or fractional
_FREE = r"-|\d[\d,]*(?:\.\d+)?"             # free: "-" or a number
# product row: <description>  QTY  FREE  RATE  AMOUNT
_ROW = re.compile(rf"^(.+?)\s+({_QTY})\s+({_FREE})\s+({_NUM})\s+({_NUM})\s*$")
# per-party bare subtotal: <qty> <free> <amount>  (no leading description)
_SUBTOTAL = re.compile(rf"^{_QTY}\s+{_FREE}\s+{_NUM}\s*$")

# report furniture / totals that must never become a band or product line
_SKIP_PREFIX = ("TOTAL", "GRAND TOTAL", "AREA / ITEM", "AREA/ITEM", "REPORT FOR",
                "COMPANY", "CONTINUED", "PAGE NO", "D E S C R I P T I O N")


def _line(row):
    """The single text line of a row: its lone (or merged, identical) cell, with the
    XLS non-breaking spaces flattened to plain spaces so the fixed-width regexes fire."""
    distinct = [c for c in (cell_text(x) for x in row) if c]
    if not distinct:
        return ""
    return distinct[0].replace("\xa0", " ").strip()


def detect(rows):
    head = compact(" ".join(" ".join(cell_text(c) for c in r) for r in rows[:15]))
    if "areaitemwisesalessummary" not in head:
        return False
    if "descriptionqtyfreerateamount" not in head:
        return False
    # Paren-guard: the 5S/NAVKAR variant appends a "( % )" discount column. Mirror the
    # party_pdf guard so that report stays on its own (percent) layout, not this one.
    raw_head = " ".join(" ".join(cell_text(c) for c in r) for r in rows[:15])
    if "%" in raw_head:
        return False
    return True


def parse_area_item_sales_summary(rows):
    records, party, location = [], "", ""
    for row in rows:
        s = _line(row)
        if not s or set(s) <= set("-"):
            continue
        up = s.upper()
        if up.startswith(_SKIP_PREFIX):
            continue
        # party band: leading hyphen followed by a letter (not "-123" numeric)
        if s.startswith("-") and re.match(r"^-\s*[A-Za-z]", s):
            party, location = _split_band(s[1:].strip())
            continue
        m = _ROW.match(s)
        if m:
            free = "0" if m.group(3) == "-" else m.group(3).replace(",", "")
            product = m.group(1).strip()
            if product and party:
                rec = {
                    "party_name": party,
                    "product_name": product,
                    "qty": m.group(2).replace(",", ""),
                    "free_qty": free,
                    "rate": m.group(4).replace(",", ""),
                    "amount": m.group(5).replace(",", ""),
                }
                if location:
                    rec["party_location"] = location
                records.append(rec)
            continue
        # bare per-party subtotal line -> skip silently
        if _SUBTOTAL.match(s):
            continue

    detected = {"D E S C R I P T I O N": "product_name", "QTY.": "qty",
                "FREE": "free_qty", "RATE": "rate", "AMOUNT": "amount"}
    return records, detected
