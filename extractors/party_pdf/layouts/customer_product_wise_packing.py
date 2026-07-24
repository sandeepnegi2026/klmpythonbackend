import re

# Agrawal Medical Agency "Customer-Product wise Sales" (KLM divisions). A party
# heading of the form "<CODE>-<NAME>[(<AREA>)],<CITY>[,(phone)]" (the code always
# carries a digit) is followed by product rows "<Product Name> <Packing> <Qty>
# <Freeqty> <Value>" and a "TOTAL <value>" subtotal. Product names also contain
# hyphens (NIOCLEAN-GEL), so a heading is told apart from a product row by two
# invariants: a product row ENDS in "<int> <int> <decimal>"; a heading's pre-hyphen
# code contains a digit and the line carries a comma/paren locator.

NUM = r"-?\d[\d,]*"
# qty & free may be integer or fractional (e.g. "5.50 0.50"); value ends in .dd
_QF = r"(\d[\d,]*(?:\.\d+)?)"
_ROW = re.compile(r"^(.+?)\s+" + _QF + r"\s+" + _QF + r"\s+(" + NUM + r"\.\d{2})\s*$")
_HEAD = re.compile(r"^([A-Za-z]{0,3}\d[A-Za-z0-9]*)-(.+)$")
_SKIP = re.compile(
    r"^\s*(-{3,}|TOTAL\b|GRAND\b|Product\s+Name\b|Page\s*No|Powered\s+By|"
    r".*Customer-Product\s+wise|.*\bUpto\b.*\d{4}|Freeqty)",
    re.I,
)


def _split_head(rest):
    """rest = '<NAME>[(<AREA>)],<CITY>[,(phone)]' -> (name, city)."""
    name = re.split(r"[(,]", rest, 1)[0].strip()
    city = ""
    # drop parenthetical groups then take the last letter-bearing comma segment
    flat = re.sub(r"\([^)]*\)", "", rest)
    segs = [s.strip() for s in flat.split(",") if s.strip()]
    for s in reversed(segs[1:] if len(segs) > 1 else segs):
        if re.search(r"[A-Za-z]", s):
            city = s
            break
    return name or rest.strip(), city


def parse_customer_product_wise_packing(text):
    headers = ["Party Name", "Area", "Product Name", "Pack", "Qty", "Free", "Amount"]
    rows = []
    party = None
    area = ""
    for ln in text.split("\n"):
        s = ln.strip()
        if not s:
            continue
        if _SKIP.match(s):
            continue
        m = _ROW.match(s)
        if m and party is not None:
            # packing is glued into the product name in this ERP; keep them together
            # (canonical-name enrichment handles the pack suffix downstream).
            rows.append([party, area, m.group(1).strip(), "", m.group(2), m.group(3), m.group(4)])
            continue
        hm = _HEAD.match(s)
        if hm and ("," in s or "(" in s) and not _ROW.match(s):
            cand_name, cand_area = _split_head(hm.group(2))
            # An ADDRESS continuation line ("2-A, GROUND FLOOR RANISATI NGR,") also
            # matches _HEAD (code '2', name 'A') and would clobber the real heading
            # ("97814-PHARMACY NO. 1,JAIPUR") with a phantom 1-letter party. A real
            # customer name is never a 1-2 char fragment -> only accept longer names.
            if len(cand_name) >= 3:
                party, area = cand_name, cand_area
            continue
    return headers, rows
