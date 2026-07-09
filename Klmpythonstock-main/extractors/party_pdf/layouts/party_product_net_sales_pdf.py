"""Marg ERP 9+ "Party/Product Wise Net Sales" report (BADAL ENTERPRISE style).

Header block:
    M/S <name> / address / Phone.. E-Mail.. / GSTIN..
    Party/Product Wise Net Sales From dd-mm-yyyy To dd-mm-yyyy
    -----
    Party/Product Name   Sale Qty   Ret Qty   Net Qty
    -----

Body: repeating blocks of a bare PARTY band row (text only, no trailing numbers,
e.g. "PRIME TARDERS 23-24") followed by product line rows

    <product name incl pack like 1*10>  <SaleQty>  <RetQty>  <NetQty>

ending in "Party Total" and "Grand Total" (e.g. 2864 / 0 / 2864).

Three trailing quantity columns:  Sale Qty (=qty), Ret Qty (=return, all 0 here),
Net Qty (=Sale-Ret).  There is NO amount / rate / value column, NO free column and
NO invoice/date, so only party_name / product_name / qty are emitted; the value
dimension is intentionally left empty (a soft CORE_FIELD_EMPTY / AMBER is correct —
the vendor simply prints no value, and inventing one would be wrong).

Party bands and product rows are told apart by look-ahead exactly like the sibling
`product_party_wise_list` layout: a TEXT line whose next significant line is a
PRODUCT row is a party heading; product rows carry the current party down.  The PDF
is a plain space-aligned single text column, so a flat text parse is sufficient
(no positional x-bucketing needed).
"""
import re

_NUM = r"-?\d[\d,]*\.?\d*"
# product row: <name (may contain packs like 1*10)>  SaleQty  RetQty  NetQty
_PRODUCT = re.compile(
    r"^(.*?\S)\s+(" + _NUM + r")\s+(" + _NUM + r")\s+(" + _NUM + r")$"
)
# band-level total rows (also carry three trailing numbers, so match BEFORE _PRODUCT)
_TOTAL = re.compile(r"^(party|grand)\s+total\b", re.I)
# repeating page furniture / header block / rules / footers
_SKIP = re.compile(
    r"^(m/s\b|phone\s*:|gstin\s*:|party\s*/\s*product\s+wise\s+net\s+sales|"
    r"party\s*/\s*product\s+name|from\s*:|continued\.|page\s*no|"
    r"\*\*\*|-{5,}|=+$)",
    re.I,
)
# address / e-mail lines that lack the "M/S"/"Phone" prefix but are still furniture
_ADDR = re.compile(r"e-\s*mail\s*:", re.I)
# masthead address line (repeats under the M/S line on every page): begins with a
# house/plot number + comma, e.g. "49,NETAJI SARANI, ...". Never a party heading.
_MASTHEAD_ADDR = re.compile(r"^\d+\s*,")


def parse_party_product_net_sales_pdf(text):
    headers = ["Party Name", "Product Name", "Sale Qty"]
    lines = [ln.strip() for ln in text.split("\n")]

    kinds = []
    for idx, s in enumerate(lines):
        prev = lines[idx - 1].strip() if idx > 0 else ""
        if not s:
            kinds.append("BLANK")
        elif _TOTAL.match(s):
            kinds.append("TOTAL")
        elif _SKIP.match(s) or _ADDR.search(s):
            kinds.append("SKIP")
        # the line directly under an "M/S ..." masthead line is the vendor address
        elif prev[:3].lower() == "m/s" or _MASTHEAD_ADDR.match(s):
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
    party_name = ""
    have_party = False
    for i, s in enumerate(lines):
        k = kinds[i]
        if k == "PRODUCT" and have_party:
            m = _PRODUCT.match(s)
            product = m.group(1).strip()
            sale_qty = m.group(2)
            rows.append([party_name, product, sale_qty])
        elif k == "TEXT":
            # A heading whose next significant line is a product row is a party band.
            # (There is no separate division band in this report.)
            if next_significant(i) == "PRODUCT":
                party_name = s
                have_party = True
    return headers, rows
