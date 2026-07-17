import re

from extractors.party_pdf.party_area import split_gujarat_party_area

# Product row: <name> Free SaleQty. ReturnQty TotalQty Amount TotalAmt GSTAmt. GrossAmt.
# -> EIGHT trailing numbers.
_NUM = r"-?\d[\d,]*\.?\d*"
_PRODUCT = re.compile(
    r"^(.*?\S)\s+"
    + r"\s+".join(["(" + _NUM + ")"] * 8)
    + r"$"
)
# Party / Mfg.Company / Company / Grand Total: subtotal footers (all dropped).
_TOTAL = re.compile(r"^(party|mfg\.?\s*company|company|grand)\s*total\s*:", re.I)
# Repeating page furniture: column header, report title, date range,
# "n/m" page number, and long number/comma phone lines.
_SKIP = re.compile(
    r"^(product\s+free\s+saleqty|product\s*\+\s*party\s*wise|from\s*:|"
    r"\d+\s*/\s*\d+$|[\d,]{6,}$)",
    re.I,
)
# A page-banner phone line, e.g. "9825517971,,9825517971": starts with a long
# digit run and contains only digits, commas, dashes, dots, slashes, spaces.
_PHONE = re.compile(r"^\d{6,}[\d,./ -]*$")
# Company / division band, e.g. "KLM (?)", "KLM LAB (07)", "KLM LAB (09)": a
# short line ending in a parenthesised numeric (or "?") company code. Party
# headings never end this way, so this is an unambiguous discriminator.
_BAND = re.compile(r"^(.*?\S)\s*\((\?|\d+)\)$")


def parse_product_party_wise_totqty_gst(text):
    """Marg 'Product + Party Wise List Report', 8-column Free/SaleQty/ReturnQty/
    TotalQty/Amount/TotalAmt/GSTAmt/GrossAmt variant (STOCKWELL PHARMA, KLM).

    Exact column header (gate token
    ``productfreesaleqty.returnqtytotalqtyamounttotalamtgstamt.grossamt.``):

        Product Free SaleQty. ReturnQty TotalQty Amount TotalAmt GSTAmt. GrossAmt.

    Nesting:
        COMPANY / division band ("KLM (?)", "KLM LAB (07)")
          -> PARTY heading ("ABHINANDAN PHARMACY 16.RUBY COMPLEX...NAVSARI,")
             -> product rows
                -> Party/Mfg.Company/Grand Total: subtotals.

    This differs from its siblings only by column count:
      * product_party_wise_freeamt3 (AARCHI) has THREE trailing numbers,
      * product_party_wise_list (AKSHAR) has FOUR, and
      * product_party_wise_freeamt (MANISH) has FIVE.
    Here there are EIGHT trailing numbers, so none of them parse a product row
    (they leave numeric columns glued onto the product name), which is why this
    file yields 0 rows on every existing layout.

    Column mapping (qty and value kept strictly separate; no qty derived from a
    value column):
      * Free      -> free (free QTY)
      * TotalQty  -> qty  (net transacted qty = Free + SaleQty - ReturnQty;
                            pure-return rows print this negative, and the
                            matching GrossAmt. is negative too, so qty and value
                            stay sign-consistent)
      * GrossAmt. -> amount (final value incl. GST; matches TotalQty's sign)
    SaleQty./ReturnQty/Amount/TotalAmt/GSTAmt. are the intermediate breakdown
    columns and are not remapped (the net TotalQty and GrossAmt. are the
    canonical qty/value pair).

    Company/division bands ("KLM LAB (07)") and party headings (bare
    "<NAME> <ADDRESS>" lines) are told apart by look-ahead: a PARTY block is the
    first TEXT line after a band/total that is followed by product rows; any
    further TEXT lines before the first product are wrapped address
    continuations and are appended to the heading before the name/area split.
    """
    headers = ["Division", "Party Name", "Area", "Product Name",
               "Free", "Qty", "Amount"]
    lines = [ln.strip() for ln in text.split("\n")]

    # Self-calibrate the repeating page banner: the first content line is the
    # vendor name; on every page the banner runs from that vendor line through
    # the "Product Free SaleQty. ..." column header. Mark the whole block SKIP
    # so no banner line is mistaken for a party heading.
    banner = ""
    for ln in lines:
        if ln:
            banner = ln
            break

    in_banner = False
    kinds = []
    for s in lines:
        if banner and s == banner:
            in_banner = True
        if in_banner:
            kinds.append("SKIP")
            if s.lower().startswith("product free"):
                in_banner = False      # column header closes the banner block
            continue
        if not s:
            kinds.append("BLANK")
        elif _PHONE.match(s):
            kinds.append("SKIP")
        elif _TOTAL.match(s):
            kinds.append("TOTAL")
        elif _SKIP.match(s):
            kinds.append("SKIP")
        elif _PRODUCT.match(s):
            kinds.append("PRODUCT")
        elif _BAND.match(s):
            kinds.append("BAND")
        else:
            kinds.append("TEXT")

    rows = []
    division = ""
    party_name = party_area = ""
    have_party = False
    # pending_heading accumulates the (possibly multi-line) party heading that
    # precedes the first product row of a block.
    pending_heading = ""

    for i, s in enumerate(lines):
        k = kinds[i]
        if k == "PRODUCT":
            if pending_heading:
                party_name, party_area = split_gujarat_party_area(pending_heading)
                pending_heading = ""
                have_party = True
            if have_party:
                m = _PRODUCT.match(s)
                # groups: 1=name 2=Free 3=SaleQty 4=ReturnQty 5=TotalQty
                #         6=Amount 7=TotalAmt 8=GSTAmt 9=GrossAmt
                rows.append(
                    [division, party_name, party_area, m.group(1),
                     m.group(2), m.group(5), m.group(9)]
                )
        elif k == "TOTAL":
            pending_heading = ""       # block closed; next TEXT starts fresh
        elif k == "BAND":
            division = _BAND.match(s).group(1).strip() or s
            pending_heading = ""
        elif k == "TEXT":
            # party heading line(s): first line + any wrapped address lines
            pending_heading = (pending_heading + " " + s).strip() if pending_heading else s
    return headers, rows
