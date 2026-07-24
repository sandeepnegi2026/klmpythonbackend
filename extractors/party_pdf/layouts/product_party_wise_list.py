import re

from extractors.party_pdf.party_area import split_gujarat_party_area

_NUM = r"-?\d[\d,]*\.?\d*"
# product row: <name (may contain packs like 1*10)> Free SaleQty ReturnQty Amount
_PRODUCT = re.compile(
    r"^(.*?\S)\s+(" + _NUM + r")\s+(" + _NUM + r")\s+(" + _NUM + r")\s+(" + _NUM + r")$"
)
_TOTAL = re.compile(r"^(party|mfg\.?company|company|grand)\s*total\s*:", re.I)
# Division band: "KLM.COSMO*" (AKSHAR) / "KLM [COSMO DIVISION]" (N.K.MEDICAL). The
# char after KLM (. [ or () distinguishes it from any real shop name starting "KLM".
_DIVISION = re.compile(r"^KLM\s*[.\[(]", re.I)
# A wrapped PRODUCT-pack tail on its own line ("125ML", "150ML", "1*10") — a data-row
# continuation of the product above, NOT a party heading.
_PACK_TAIL = re.compile(r"^(\d+\s*(?:ML|GM|GMS|MG|KG|GC|LTR|G|L|N|S|TAB|CAP)\.?|\d+\s*\*\s*\d+)$", re.I)
_DIV_NAME = re.compile(r"\[\s*([A-Za-z]+)\s+DIVISION|^KLM\s*\.?\s*([A-Za-z]+)", re.I)


def _clean_division(s):
    """"KLM [COSMO DIVISION]" / "KLM.COSMO*" -> "COSMO" (matches the catalog form used
    for matched products; raw markers only ever surface on UNmatched products)."""
    m = _DIV_NAME.search(s)
    return (m.group(1) or m.group(2)).upper() if m else s
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

    # Three kinds of TEXT line must be told apart (the old last-TEXT-before-a-PRODUCT
    # heuristic conflated them, so a wrapped party heading's 2nd line — e.g. a bare
    # "SURAT"/"ROAD" address tail — became the party while its 1st line leaked into
    # division):
    #   * DIVISION band  -> "KLM.COSMO*" (AKSHAR) or "KLM [COSMO DIVISION]" (N.K.).
    #   * page FURNITURE -> the stockist name/address/phone/title block that repeats
    #     verbatim atop every page (everything before the FIRST division band).
    #   * PARTY heading  -> one OR MORE consecutive TEXT lines (address wraps) that
    #     immediately precede the party's PRODUCT rows; coalesced into one heading.
    first_div = next((i for i, s in enumerate(lines) if _DIVISION.match(s)), len(lines))
    furniture = {lines[i] for i in range(first_div) if kinds[i] == "TEXT"}

    rows = []
    division = ""
    party_name = party_area = ""
    have_party = False
    buf = []  # consecutive TEXT lines of the current (possibly wrapped) party heading
    for i, s in enumerate(lines):
        k = kinds[i]
        if k == "PRODUCT":
            if buf:
                party_name, party_area = split_gujarat_party_area(" ".join(buf))
                have_party = True
                buf = []
            if have_party:
                m = _PRODUCT.match(s)
                rows.append(
                    [division, party_name, party_area, m.group(1),
                     m.group(2), m.group(3), m.group(5)]
                )
        elif k == "TEXT":
            if _DIVISION.match(s):
                division = _clean_division(s)
                buf = []
                have_party = False
            elif s in furniture or _PACK_TAIL.match(s):
                continue          # repeated page-header OR a wrapped product-pack tail
            else:
                buf.append(s)     # party heading line (accumulate wrap continuations)
        elif k == "TOTAL":
            buf = []              # end of this party's product block
    return headers, rows
