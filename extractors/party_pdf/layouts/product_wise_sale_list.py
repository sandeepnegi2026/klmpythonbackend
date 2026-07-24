import re

from extractors.party_pdf.party_area import split_gujarat_party_area

_NUM = r"-?\d[\d,]*\.?\d*"
# product row: <name+pack> Qty Free Repl S.Value Tot.Value
# (the name and pack are glued in one run; a long name WRAPS to the next line,
# which carries only the name TAIL — the five numbers are always on THIS line).
_PRODUCT = re.compile(
    r"^(.*?\S)\s+(" + _NUM + r")\s+(" + _NUM + r")\s+(" + _NUM + r")\s+("
    + _NUM + r")\s+(" + _NUM + r")$"
)
# the column header row: "Product Pack Qty. Free Repl. S.Value Tot.Value".
_HEADER = re.compile(r"^product\s+pack\s+qty", re.I)
# "Customer Total 32 0 0 6278.65 6414.35" ends a party's product block.
_CUST_TOTAL = re.compile(r"^(customer|party|grand)\s*total\b", re.I)
# repeating furniture: the column header, the report title, and page markers.
_SKIP = re.compile(
    r"^(product\s+pack\s+qty|product\s*wise\s*sale\s*list|for\s+the\s+period|"
    r"page\s*\d+$|\d+\s*/\s*\d+$)",
    re.I,
)


def parse_product_wise_sale_list(text):
    """Marg 'Product wise sale list' (J.K.MEDICO / SAURASHTRA style).

    Nesting:  <PARTY heading (may wrap)>  ->  product rows  ->  Customer Total.
    Columns per product row:  Product+Pack | Qty | Free | Repl | S.Value | Tot.Value.

    There are no division bands — every product is KLM's. A product name that is too
    long WRAPS: the five numbers stay on the first line, the name TAIL lands on the
    next (bare-text) line. A bare-text line is therefore either a name-wrap tail (when
    we are inside a party's product block) or a PARTY heading (at the start or right
    after a Customer Total). Repl (replacement qty) has no canonical field; Tot.Value
    (the gross amount billed, incl. tax) is taken as the sale amount, matching the
    'last money column = amount' convention of the sibling product-wise layouts."""
    headers = ["Party Name", "Area", "Product Name", "Qty", "Free", "Amount"]
    lines = [ln.strip() for ln in text.split("\n")]

    # Page FURNITURE: the stockist name / address / title block that repeats verbatim
    # atop every page, BEFORE the column-header row. Collect the bare-text lines above
    # the first header row and skip them wherever they recur, so the company block never
    # leaks into the first party heading (the party heading sits AFTER the header row).
    first_header = next((i for i, s in enumerate(lines) if s and _HEADER.match(s)), 0)
    furniture = {s for s in lines[:first_header]
                 if s and not _SKIP.match(s) and not _CUST_TOTAL.match(s)
                 and not _PRODUCT.match(s)}

    rows = []
    party_name = party_area = ""
    have_party = False        # inside a party's product block (heading seen, no total yet)
    in_block = False          # a product row has been emitted for this party
    buf = []                  # consecutive TEXT lines of a (possibly wrapped) party heading

    def flush_party():
        nonlocal party_name, party_area, have_party, in_block, buf
        if buf:
            party_name, party_area = split_gujarat_party_area(" ".join(buf))
            have_party = True
            in_block = False
            buf = []

    for s in lines:
        if not s or _SKIP.match(s) or s in furniture:
            continue
        if _CUST_TOTAL.match(s):
            # end of this party's block; next TEXT line starts a new party heading
            have_party = False
            in_block = False
            buf = []
            continue
        m = _PRODUCT.match(s)
        if m:
            flush_party()
            if not have_party:
                continue          # a numeric line with no party context -> skip
            name = m.group(1)
            rows.append([party_name, party_area, name, m.group(2), m.group(3), m.group(6)])
            in_block = True
            continue
        # bare-text line
        if have_party and in_block:
            # name-wrap tail of the product just emitted -> append to its name
            if rows:
                rows[-1][2] = (rows[-1][2] + " " + s).strip()
            continue
        # otherwise it's (part of) a party heading
        buf.append(s)

    return headers, rows
