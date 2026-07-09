import re
from collections import defaultdict

# "AREA / ITEM WISE SALES SUMMARY" party layout (AGARTALA PHARMA LLP / KLM export).
# Distinct from the NAVKAR-style ``area_item_summary`` which carries a trailing
# discount ``( % )`` column: THIS variant has exactly four numeric columns and the
# compact header ``descriptionqty.freerateamount`` (no percent column).
#
# Structure:
#   -<PARTY NAME + LOCATION>                 (band, leading hyphen)
#       <PRODUCT ...>  QTY  FREE  RATE  AMOUNT   (free may be "-")
#       ...
#       <qty> <free> <amount>                (bare per-party subtotal -> skip)
#   TOTAL : <qty> <free> <amount>            (area / group subtotal -> skip)
#   GRAND TOTAL : <qty> <free> <amount>      (report total -> skip)
#
# MAPPING: party_name = band text (leading '-' stripped) with the trailing town
# peeled off; Area = town; product_name; qty; free_qty (free, '-' -> 0); rate; amount.
#
# The band has NO delimiter between the party name and its town/area -- the town
# is simply the trailing word(s) (e.g. "ABANTIKA MEDICAL HALL KASHIPUR",
# "AGARTALA MEDICAL OFFICE LANE"). We split it document-driven: a first pass
# learns which trailing unigrams / bigrams RECUR across distinct parties (towns
# repeat -- BATTALA, DHALESWAR, OFFICE LANE, CENTRAL ROAD...), then each band is
# peeled preferring a recurring bigram, then a generic locality suffix, then a
# recurring unigram, then a guarded single last token. A business/entity word
# (HALL, MEDICAL, PHARMACY...) is never peeled, so a town-less band like
# "SAI MEDICAL HALL" keeps an empty Area rather than corrupting the name.

_NUM = r"[\d,]+\.\d+"                       # rate / amount always carry decimals
_QTY = r"\d[\d,]*(?:\.\d+)?"                # qty: integer or fractional
_FREE = r"-|\d[\d,]*(?:\.\d+)?"             # free: "-" or a number
# product row: <description>  QTY  FREE  RATE  AMOUNT
_ROW = re.compile(rf"^(.+?)\s+({_QTY})\s+({_FREE})\s+({_NUM})\s+({_NUM})\s*$")
# per-party bare subtotal: <qty> <free> <amount>  (no leading description)
_SUBTOTAL = re.compile(rf"^{_QTY}\s+{_FREE}\s+{_NUM}\s*$")

# Entity/form words that must never be treated as a town (they belong to the
# business name). If the trailing token is one of these, Area stays empty.
_BIZ = {
    "HALL", "MEDICAL", "MEDICALS", "MEDICAL'S", "PHARMACY", "PHARMA", "DRUGS",
    "DRUG", "MEDICOS", "MEDICINE", "MEDICINES", "CHEMIST", "DRUGGIST",
    "ENTERPRISE", "STORES", "STORE", "SURGICAL", "SURGICALS", "CARE", "POINT",
    "TRADERS", "CONCERN", "LIFECARE", "PHARMACEUTICALS", "MEDI", "WORLD",
    "CORNER", "EXPRESS", "CENTER", "CENTRE", "HOUSE", "LLP", "AGENCY",
    "AGENCIES", "MR", "STAFF", "MADICAL", "MEDACAL", "PHARMACO", "LIFE", "LINE",
    "DIVINE", "MEDIWORLD", "MEDISHOP", "MEDIHUT", "MEDZONE", "MEDICITY",
    "MEDIPOINT", "MED",
}
# Generic locality suffixes whose town is usually the trailing TWO words
# (e.g. "OFFICE LANE", "CENTRAL ROAD", "MATH CHOWMUHANI", "BIJOY KUMAR").
_SUFFIX = {
    "ROAD", "LANE", "LINE", "NAGAR", "BAZAR", "BAZAAR", "KUMAR", "MURA", "CLUB",
    "CHOUMUHANI", "CHOWMUHANI", "CHOUMUHAN", "CHOWMUHAN", "CHOUMUHA", "CHOWMAN",
    "ASRAM", "ASHRAM",
}


def _clean_tok(tok):
    # Drop a leading parenthetical like "(CREDIT)KHOWAI" -> "KHOWAI".
    return re.sub(r"^\([^)]*\)", "", tok)


def _peelable(tok):
    t = _clean_tok(tok).rstrip(".").upper()
    if t in _BIZ:
        return False
    # letters (dots/apostrophes allowed for G.B.BAZAR / R.M.S), optional -digit tail
    return bool(re.match(r"^[A-Z][A-Z.'&]*(?:-\d+)?$", t))


def _band_town_sets(bands):
    """Learn trailing unigrams / bigrams that recur across >=2 distinct parties."""
    uni, bi = defaultdict(set), defaultdict(set)
    for b in bands:
        tk = b.split()
        if len(tk) >= 2:
            uni[_clean_tok(tk[-1]).rstrip(".").upper()].add(" ".join(tk[:-1]))
        if len(tk) >= 3:
            bi[(tk[-2].upper(), _clean_tok(tk[-1]).rstrip(".").upper())].add(" ".join(tk[:-2]))
    uni_f = {k for k, v in uni.items() if len(v) >= 2}
    bi_f = {k for k, v in bi.items() if len(v) >= 2}
    return uni_f, bi_f


def _split_party_town(name, uni_f, bi_f):
    tk = name.split()
    if len(tk) < 2:
        return name, ""
    lastU = _clean_tok(tk[-1]).rstrip(".").upper()
    biK = (tk[-2].upper(), lastU) if len(tk) >= 3 else None
    # 1. recurring bigram town
    if biK and biK in bi_f and _peelable(tk[-2]):
        return " ".join(tk[:-2]), (_clean_tok(tk[-2]) + " " + _clean_tok(tk[-1])).strip().rstrip(".")
    # 2. generic locality suffix -> capture trailing two words
    if lastU in _SUFFIX and len(tk) >= 3 and _peelable(tk[-2]):
        return " ".join(tk[:-2]), (_clean_tok(tk[-2]) + " " + _clean_tok(tk[-1])).strip().rstrip(".")
    # 3. recurring unigram town
    if lastU in uni_f and _peelable(tk[-1]):
        return " ".join(tk[:-1]), _clean_tok(tk[-1]).rstrip(".")
    # 4. guarded single last-token peel (unique towns); never a generic suffix alone
    if _peelable(tk[-1]) and lastU not in _SUFFIX:
        return " ".join(tk[:-1]), _clean_tok(tk[-1]).rstrip(".")
    return name, ""


def parse_area_item_sales_summary(text):
    H = ["Party Name", "Area", "Product Name", "Qty", "Free", "Rate", "Amount"]
    lines = text.split("\n")
    # pass 1: collect party bands to learn recurring town tokens
    bands = []
    for raw in lines:
        s = raw.strip()
        if s.startswith("-") and re.match(r"^-\s*[A-Za-z]", s):
            bands.append(s[1:].strip())
    uni_f, bi_f = _band_town_sets(bands)

    rows, party, area = [], "", ""
    for raw in lines:
        s = raw.strip()
        if not s or set(s) <= set("-"):
            continue
        up = s.upper()
        # report furniture / totals
        if up.startswith(("TOTAL", "GRAND TOTAL", "AREA / ITEM", "REPORT FOR",
                          "COMPANY :", "CONTINUED", "PAGE NO", "D E S C R I P T I O N")):
            continue
        # party band: leading hyphen followed by a letter (not "-123" numeric)
        if s.startswith("-") and re.match(r"^-\s*[A-Za-z]", s):
            party, area = _split_party_town(s[1:].strip(), uni_f, bi_f)
            continue
        m = _ROW.match(s)
        if m:
            free = "0" if m.group(3) == "-" else m.group(3).replace(",", "")
            rows.append([
                party,
                area,
                m.group(1).strip(),
                m.group(2).replace(",", ""),
                free,
                m.group(4).replace(",", ""),
                m.group(5).replace(",", ""),
            ])
            continue
        # bare per-party subtotal line -> skip silently
        if _SUBTOTAL.match(s):
            continue
    return H, rows
