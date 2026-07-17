import re

from extractors.party_pdf.party_area import split_gujarat_party_area

# Product row: <name> Free SaleQty. Amount  (THREE trailing numbers).
_NUM = r"-?\d[\d,]*\.?\d*"
_PRODUCT = re.compile(
    r"^(.*?\S)\s+(" + _NUM + r")\s+(" + _NUM + r")\s+(" + _NUM + r")$"
)
# Party / Mfg.Company / Company / Grand Total: subtotal footers (all dropped).
_TOTAL = re.compile(r"^(party|mfg\.?\s*company|company|grand)\s*total\s*:", re.I)
# Repeating page furniture: column header, report title, date range,
# "n/m" page number, and long number/comma address & phone lines.
_SKIP = re.compile(
    r"^(product\s+free\s+saleqty|product\s*\+\s*party\s*wise|from\s*:|"
    r"\d+\s*/\s*\d+$|[\d,]{7,}$)",
    re.I,
)
# A page-banner phone line, e.g. "9825783406,,0261-2532320,9081122223":
# starts with a long digit run and contains only digits, commas, dashes,
# dots, slashes and spaces. No party name or product row looks like this.
_PHONE = re.compile(r"^\d{6,}[\d,./ -]*$")


def parse_product_party_wise_freeamt3(text):
    """Marg 'Product + Party Wise List Report', 3-column Free/SaleQty/Amount variant
    (AARCHI / ARCHI DISTRIBUTOR, KLM distributor).

    Exact column header:  ``Product Free SaleQty. Amount``  (gate token
    ``productfreesaleqty.amount``).

    Nesting:
        COMPANY band ("KLM LABORATORIES -- COSMO")
          -> PARTY heading ("HEAVEN MEDICAL BARODA PRISTEG")
             -> product rows
                -> Party/Mfg.Company/Grand Total: subtotals.

    Columns per product row are exactly THREE trailing numbers:
        Product | Free | SaleQty. | Amount
    This is what separates this variant from its siblings:
      * product_party_wise_list  (AKSHAR) has FOUR numbers
        (Free | SaleQty | ReturnQty | Amount), and
      * product_party_wise_freeamt (MANISH) has FIVE numbers
        (Free | FreeAmt. | SaleQty. | Amount | TotalAmt).
    Running either sibling here would glue a numeric column into the product
    name or mis-map the money column, so this needs its own 3-number parser.

    Free (free QTY) -> free_qty and SaleQty. -> qty are the two genuine quantity
    columns; Amount -> amount is the sole value column. No quantity is ever
    derived from the value column.

    Company bands ("KLM LABORATORIES -- COSMO") and party headings (bare
    "<NAME> <AREA>" lines) are told apart by look-ahead: a PARTY heading is
    followed by product rows, a COMPANY band is followed by another heading.
    The division token after ' -- ' (e.g. "COSMO") is kept.
    """
    headers = ["Division", "Party Name", "Area", "Product Name",
               "Free", "Qty", "Amount"]
    lines = [ln.strip() for ln in text.split("\n")]

    # Self-calibrate the repeating page banner: the first content line is the
    # vendor name. On every page the banner block runs from the vendor line
    # through the "Product Free SaleQty. Amount" column header (vendor,
    # 1-2 address lines, phone, From:, title, header) — a variable number of
    # address lines. Mark the whole block SKIP so no banner line is mistaken
    # for a party heading.
    banner = ""
    for ln in lines:
        if ln:
            banner = ln
            break

    in_banner = False
    kinds = []
    for idx, s in enumerate(lines):
        if banner and s == banner:
            in_banner = True          # start of a page banner block
        if in_banner:
            kinds.append("SKIP")
            if _SKIP.match(s) and s.lower().startswith("product free"):
                in_banner = False     # column header closes the banner block
            continue
        if not s:
            kinds.append("BLANK")
        elif _PHONE.match(s):
            kinds.append("SKIP")      # stray phone line
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
                 m.group(2), m.group(3), m.group(4)]
            )
        elif k == "TEXT":
            if " -- " in s:
                # company band: "KLM LABORATORIES -- COSMO" -> division "COSMO"
                division = s.split(" -- ", 1)[1].strip() or s
            elif next_significant(i) == "PRODUCT":
                party_name, party_area = split_gujarat_party_area(s)
                have_party = True
    return headers, rows
