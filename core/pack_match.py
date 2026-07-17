import re

# A pack/size is always NUMBER-LED — a measure ("60ML", "15GM", "5MG"), a counted
# container ("7TAB", "1 BOX"), or a strip/blister count ("1*10", "10'S", "10X10").
# It is NEVER a bare dosage-FORM word: "LOTION", "CREAM", "SOAP", "GEL", "DROPS",
# "OINT", "SYP", "SUSP" are part of the PRODUCT NAME, not the pack. Treating them as
# pack (the old regex did, with an optional leading number) truncated names like
# "IMXIA 5 LOTION" -> "IMXIA" and "Kenz Soap" -> "Kenz", which then mis-matched the
# product master (e.g. -> "Imxia 10"). Every alternative below therefore requires a
# leading digit/count, and the form words are gone. This regex matches a strict
# SUBSET of the previous one, so it can only ever peel LESS, never introduce a new
# over-peel — verified to be 0/303 form-strips over the whole product_master catalog
# and its ~6k harvested spellings (tests/test_pack_match.py).
PACK_RE = re.compile(
    r"^(?:"
    r"(?:TAB|CAP)\s*\d+"                                        # leading form+count: "TAB 10"
    r"|\d+(?:\.\d+)?\s*(?:ML|GM|GMS|MG|G)"                      # measure: 60ML 15GM 5MG 30G
    r"|\d+\s*(?:TAB|CAP|PCS|BOX|KIT|SACHET|TUBE|NOS|STR|STP)"   # counted container: 7TAB 1BOX
    r"|1\*\d+"                                                   # strip: 1*10
    r"|[1-9]X\d+(?:[A-Z]+)?"                                     # grid: 10X10 / 5X6ML
    r"|\d+'?S"                                                   # blister count: 10'S 10S
    r")$",
    re.I,
)


def extract_pack_from_product(product):
    """
    Extracts the pack/size information from the end of a product name string.
    Returns a tuple of (product_name_without_pack, pack).

    Only a genuine measure/count suffix is peeled (see PACK_RE); dosage-form words
    are left as part of the name.
    """
    if not product:
        return "", ""

    tokens = product.strip().split()

    # Check 2-token suffix first (e.g. "50 GM")
    if len(tokens) >= 3 and PACK_RE.match(tokens[-2] + tokens[-1]):
        return " ".join(tokens[:-2]), " ".join(tokens[-2:])

    # Then check 1-token suffix (e.g. "50GM")
    if len(tokens) >= 2 and PACK_RE.match(tokens[-1]):
        return " ".join(tokens[:-1]), tokens[-1]

    return product, ""
