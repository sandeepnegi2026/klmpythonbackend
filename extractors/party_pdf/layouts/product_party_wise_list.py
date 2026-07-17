import re

from extractors.party_pdf.party_area import split_gujarat_party_area

_NUM = r"-?\d[\d,]*\.?\d*"
# product row: <name (may contain packs like 1*10)> Free SaleQty ReturnQty Amount
_PRODUCT = re.compile(
    r"^(.*?\S)\s+(" + _NUM + r")\s+(" + _NUM + r")\s+(" + _NUM + r")\s+(" + _NUM + r")$"
)
_TOTAL = re.compile(r"^(party|mfg\.?company|company|grand)\s*total\s*:", re.I)
# repeating page furniture: column header, report title, date range, phone, page no.
_SKIP = re.compile(
    r"^(product\s+free\s+saleqty|product\s*\+\s*party\s*wise|from\s*:|"
    r"\d+\s*/\s*\d+$|[\d,]{6,}$)",
    re.I,
)


def parse_product_party_wise_list(text):
    """Marg 'Product + Party Wise List Report' (AKSHAR MEDICINES style).

    Nesting:  KLM.<DIVISION>  ->  <PARTY heading>  ->  product rows  ->  Party Total:
    Columns per product row:  Product | Free | SaleQty. | ReturnQty | Amount.

    Company bands and party headings are both bare text lines; they're told apart
    by look-ahead — a PARTY is followed by product rows, a company BAND is followed
    by another heading. ReturnQty is dropped (no canonical field; always 0 here).
    """
    headers = ["Division", "Party Name", "Area", "Product Name", "Free", "Qty", "Amount"]
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
    party_name = party_area = ""
    have_party = False
    for i, s in enumerate(lines):
        k = kinds[i]
        if k == "PRODUCT" and have_party:
            m = _PRODUCT.match(s)
            rows.append(
                [division, party_name, party_area, m.group(1),
                 m.group(2), m.group(3), m.group(5)]
            )
        elif k == "TEXT":
            if next_significant(i) == "PRODUCT":
                party_name, party_area = split_gujarat_party_area(s)  # party heading
                have_party = True
            else:
                division = s       # company/mfg band (another heading follows)
    return headers, rows
