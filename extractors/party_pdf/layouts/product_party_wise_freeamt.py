import re

_NUM = r"-?\d[\d,]*\.?\d*"
# product row: <name> Free FreeAmt. SaleQty. Amount TotalAmt  (5 trailing numbers).
# The name may itself carry '=' (e.g. "KLM-C-1000=1X20 TAB") or '-' packs, so the
# name is captured non-greedily up to the FIVE anchored numeric columns.
_PRODUCT = re.compile(
    r"^(.*?\S)\s+(" + _NUM + r")\s+(" + _NUM + r")\s+(" + _NUM + r")\s+(" + _NUM
    + r")\s+(" + _NUM + r")$"
)
# Party / Mfg.Company / Company / Grand Total: subtotal footers (all dropped).
_TOTAL = re.compile(r"^(party|mfg\.?\s*company|company|grand)\s*total\s*:", re.I)
# repeating page furniture: column header, report title, date range, phone,
# vendor banner, "n/m" page number, and the long comma address line.
_SKIP = re.compile(
    r"^(product\s+free\s+freeamt|product\s*\+\s*party\s*wise|from\s*:|"
    r"\d+\s*/\s*\d+$|[\d,]{7,}$)",
    re.I,
)
# trailing Marg direction glyphs "<", ">", "<>", "/>" left on the band tail.
_BAND_MARK = re.compile(r"\s*[<>/]+\s*$")


def _split_band(raw):
    """Split a '<NAME>=<AREA>' Marg band into (name, area), tolerating spaces
    around '=' and the trailing '<' / '>' / '<>' / '/>' direction glyphs Marg
    prints on some bands. Falls back to a trailing '-<AREA>' split, else the
    whole string is the name (area blank)."""
    s = _BAND_MARK.sub("", (raw or "").strip()).strip()
    if "=" in s:
        name, area = s.split("=", 1)
        return name.strip(" .-,"), area.strip(" .-,")
    if "-" in s:
        head, _, tail = s.rpartition("-")
        tail = tail.strip(" .-,")
        # only treat the hyphen tail as an area when it is a short alpha token
        # (a locality), never when it is a product-code fragment or number.
        if head.strip() and re.fullmatch(r"[A-Za-z][A-Za-z .]{1,}", tail):
            return head.strip(" .-,"), tail
    return s, ""


def parse_product_party_wise_freeamt(text):
    """Marg 'Product + Party Wise List Report', FreeAmt/TotalAmt 5-column variant
    (MANISH MEDICAL AGENCIES, KLM distributor).

    Nesting:  COMPANY band ("KLM=COSMO")  ->  PARTY band ("AKASH MEDICAL STORES=
    GADHPUR")  ->  product rows  ->  Party/Mfg.Company/Grand Total: subtotals.

    Columns per product row are
        Product | Free | FreeAmt. | SaleQty. | Amount | TotalAmt
    i.e. FIVE trailing numbers. The distinct FreeAmt. (free-value) and TotalAmt
    (net) columns are what separate this from the sibling
    product_party_wise_list (AKSHAR), whose rows carry only FOUR numbers
    (Free | SaleQty | ReturnQty | Amount); running the AKSHAR parser here glues
    the Free qty into the product name and mis-reads the money columns.

    Free (free QTY) -> free_qty and SaleQty. -> qty are the two genuine quantity
    columns; Amount (gross) -> amount and TotalAmt (net) -> net_amount are the
    value columns. FreeAmt. is a value column with no canonical target and is
    dropped. No quantity is ever derived from a value column.

    Company bands and party bands are both bare '=' lines; they are told apart by
    look-ahead exactly like the siblings — a PARTY is followed by product rows, a
    COMPANY band is followed by another (party) band. From the company band
    "KLM=COSMO" the division token after '=' (COSMO) is kept.
    """
    headers = [
        "Division", "Party Name", "Area", "Product Name",
        "Free", "FreeAmt", "Qty", "Amount", "Net Amount",
    ]
    lines = [ln.strip() for ln in text.split("\n")]

    # The report repeats a fixed page banner on every page: <VENDOR NAME>,
    # <ADDRESS>, <PHONE>, From:..., title, column header. The phone/From/title/
    # header lines are covered by _SKIP; the vendor name and its address line are
    # not (and would otherwise be mistaken for bands). Self-calibrate: the first
    # content line is the vendor banner — skip all its recurrences and the address
    # line that always immediately follows each recurrence. No hard-coded strings.
    banner = ""
    for ln in lines:
        if ln:
            banner = ln
            break

    kinds = []
    for idx, s in enumerate(lines):
        prev = lines[idx - 1] if idx > 0 else ""
        if not s:
            kinds.append("BLANK")
        elif banner and (s == banner or prev == banner):
            kinds.append("SKIP")   # vendor banner line + its address line
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
                 m.group(2), m.group(3), m.group(4), m.group(5), m.group(6)]
            )
        elif k == "TEXT":
            if next_significant(i) == "PRODUCT":
                party_name, party_area = _split_band(s)  # party band (products follow)
                have_party = True
            else:
                # company band (another band follows): "KLM=COSMO" -> division "COSMO"
                _, div = _split_band(s)
                division = div or s
    return headers, rows
