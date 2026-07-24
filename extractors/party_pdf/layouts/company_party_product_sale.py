import re

_NUM = r"-?\d[\d,]*(?:\.\d+)?"
# product row:  <name (may contain trailing size like "... CREAM 10")>  Qty  Free  Amt
_PRODUCT = re.compile(r"^(.*?\S)\s+(" + _NUM + r")\s+(" + _NUM + r")\s+(" + _NUM + r")$")
_TOTAL = re.compile(r"^(party|company|grand)\s*total\s*:", re.I)
# repeating page furniture: column header, report title, date range, page no,
# vendor name/address/phone banner.
_SKIP = re.compile(
    r"^(company\s*/\s*party\s*/\s*product|company\s+party\s+wise|"
    r"page\s*[:\d]|.*\bpage\s+\d+\s+of\s+\d+)",
    re.I,
)


def parse_company_party_product_sale(text):
    """'Company Party Wise Product Sale Report' (RAOUSHAN PHARMA, KLM distributor).

    Nesting:  COMPANY band ("KLM DERMA")  ->  PARTY heading ("DR. ANJULA")  ->
    product rows ("CANROLFIN CREAM 30GM  10.0  4.0  2500.00")  ->  PARTY/COMPANY
    /GRAND TOTAL subtotals (all skipped).  Columns per product row are
    Product | Qty | Free | Amt.

    Company bands and party headings are both bare text lines; told apart by
    look-ahead — a PARTY is followed by product rows, a COMPANY band is followed
    by another (party) heading.
    """
    headers = ["Division", "Party Name", "Product Name", "Qty", "Free", "Amount"]
    lines = [ln.strip() for ln in text.split("\n")]

    kinds = []
    for s in lines:
        if not s:
            kinds.append("BLANK")
        elif _TOTAL.match(s):
            kinds.append("TOTAL")
        elif _SKIP.match(s):
            kinds.append("SKIP")
        elif _PRODUCT.match(s):
            kinds.append("PRODUCT")
        else:
            kinds.append("TEXT")

    def next_significant(i):
        for j in range(i + 1, len(kinds)):
            if kinds[j] in ("TEXT", "PRODUCT"):
                return kinds[j]
        return None

    rows = []
    division = ""
    party_name = ""
    have_party = False
    for i, s in enumerate(lines):
        k = kinds[i]
        if k == "PRODUCT" and have_party:
            m = _PRODUCT.match(s)
            rows.append(
                [division, party_name, m.group(1), m.group(2), m.group(3), m.group(4)]
            )
        elif k == "TEXT":
            if next_significant(i) == "PRODUCT":
                party_name = s          # party heading (products follow)
                have_party = True
            else:
                division = s            # company band (another heading follows)
    return headers, rows
