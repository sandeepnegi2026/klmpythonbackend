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

# "Container-of" dialect (KLM raw dumps): "<BRAND> TUBE OF/BOX OF/BOTTLE OF <SIZE>
# <FORM>" — e.g. "EPISERT TUBE OF 30GM CREAM", "ZYDIP C BOTTLE OF 30ML LOTION". The
# SIZE sits MID-string (a FORM word trails), so the suffix rule below never sees it
# and pack comes back empty AND the noisy name fails to match. This rule pulls the
# <SIZE> right after the container word as the pack and DROPS only the container
# filler ("TUBE OF <SIZE>"), KEEPING the form word so downstream matching can still
# pick the right form/size sibling (EKRAN 50gm has 5 forms; ZYDIP-C cream vs lotion).
# It fires ONLY when a container word is immediately followed by "OF <size>", so any
# name without that exact shape returns byte-identical to before.
_CONTAINER = r"(?:TUBE|BOX|BOTTLE|JAR|STRIP|VIAL|BLISTER)"
_SIZE_TOKEN = (
    r"\d+\s*[\*xX]\s*\d+"                                       # grid/strip count: 1*10, 10x10
    r"|\d+(?:\.\d+)?\s*(?:MLS|ML|GMS|GM|GRAMS|GRAM|KG|LTR|G|L)\b"  # measure: 30GM, 50ML
    r"|\d+"                                                      # bare count: "10" (10 tablets)
)
_CONTAINER_OF_RE = re.compile(
    r"\b" + _CONTAINER + r"\s+OF\s+(" + _SIZE_TOKEN + r")", re.I)
# Dangling container filler with no size after it ("KLMKLIN AHA FACE WASH TUBE OF").
_DANGLING_CONTAINER_RE = re.compile(r"\s*\b" + _CONTAINER + r"\s+OF\s*$", re.I)


def extract_pack_from_product(product):
    """
    Extracts the pack/size information from a product name string.
    Returns a tuple of (product_name_without_pack, pack).

    Handles two shapes:
      1. "Container-of" dialect ("BRAND TUBE OF 30GM CREAM") — size mid-string; the
         container filler is dropped, the size becomes the pack, the form word stays.
      2. A genuine measure/count SUFFIX (see PACK_RE); dosage-form words are left as
         part of the name.
    """
    if not product:
        return "", ""

    # (1) Container-of dialect — mid-string size behind "TUBE OF"/"BOX OF"/...
    m = _CONTAINER_OF_RE.search(product)
    if m:
        pack = re.sub(r"\s+", " ", m.group(1).strip())
        name = (product[:m.start()] + " " + product[m.end():])
        name = re.sub(r"\s+", " ", name).strip()
        return name, pack
    # Dangling "... TUBE OF" with nothing after — strip it, then fall through to the
    # normal suffix peel on the cleaned name.
    d = _DANGLING_CONTAINER_RE.search(product)
    if d:
        product = re.sub(r"\s+", " ", product[:d.start()]).strip()

    tokens = product.strip().split()

    # Check 2-token suffix first (e.g. "50 GM")
    if len(tokens) >= 3 and PACK_RE.match(tokens[-2] + tokens[-1]):
        return " ".join(tokens[:-2]), " ".join(tokens[-2:])

    # Then check 1-token suffix (e.g. "50GM")
    if len(tokens) >= 2 and PACK_RE.match(tokens[-1]):
        return " ".join(tokens[:-1]), tokens[-1]

    return product, ""
