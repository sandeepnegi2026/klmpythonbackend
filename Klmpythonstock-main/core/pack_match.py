import re

PACK_RE = re.compile(
    r"^(?:(?:TAB|CAP)\s*\d+)|(?:(?:\d+(?:\.\d+)?\s*)?(?:ML|GM|GMS|MG|TAB|CAP|SYP|CREAM|LOTION|PCS|BOX|KIT|SOAP|"
    r"SACHET|OINT|DROP|DROPS|1\*\d+|[1-9]X\d+(?:[A-Z]+)?|\d+'?S|G|TUBE|SUSP|NOS|STR|STP|LOT|PES|CRE|SOA))$",
    re.I,
)

def extract_pack_from_product(product):
    """
    Extracts the pack/size information from the end of a product name string.
    Returns a tuple of (product_name_without_pack, pack).
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
