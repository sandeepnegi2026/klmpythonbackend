import re

# "COMPANY / ITEM WISE SALES SUMMARY" party layout (SUDHIR MEDICINES / KLM export).
#
# Distinct from the AREA / ITEM WISE siblings: the top-level band is a COMPANY /
# DIVISION heading ("KLM (COSMOCOR)", "KLM DERMA", "KLM PEDIA" ...), NOT an area.
# The report title is literally "COMPANY / ITEM WISE SALES SUMMARY" and the
# letter-spaced column header is "D E S C R I P T I O N QTY. FREE RATE AMOUNT ( % )"
# (six numeric columns per product row, with a trailing disc-% column). The
# area_item_sales_summary / area_item_summary detect rules require an
# "AREA / ITEM WISE" title, so this file falls through to "unknown".
#
# Gate token (compact, lowercased): "company/itemwisesalessummary" together with
# the exact six-column header run "descriptionqty.freerateamount(%)".
#
# Structure:
#   <COMPANY / DIVISION>                            (bare heading, no leading '-')
#     -<PARTY NAME>                                 (band, leading hyphen)
#         <PRODUCT ...>  QTY  FREE  RATE  AMOUNT  DISC%   (free may be "-")
#         ...
#         <qty> <free> <amount> <disc%>            (bare per-party subtotal -> skip)
#     TOTAL : <qty> <free> <amount> <disc%>        (company subtotal -> skip)
#   GRAND TOTAL : <qty> <free> <amount>            (report total -> skip)
#
# MAPPING: division = current company band; party_name = band (leading '-'
# stripped); product_name; qty; free_qty (free, "-" -> 0); rate; amount; disc%.
# qty and amount are read from separate columns -- amount is NEVER derived.

_NUM = r"-?[\d,]+\.\d+"                       # rate / amount / disc% carry decimals
_QTY = r"-|-?\d[\d,]*(?:\.\d+)?"              # qty: "-", integer or fractional
_FREE = r"-|-?\d[\d,]*(?:\.\d+)?"             # free: "-" or a number
# product row: <description>  QTY  FREE  RATE  AMOUNT  DISC%
_ROW = re.compile(
    rf"^(.+?)\s+({_QTY})\s+({_FREE})\s+({_NUM})\s+({_NUM})\s+({_NUM})\s*$"
)
# bare per-party subtotal: <qty> <free> <amount> <disc%>  (no leading description)
_SUBTOTAL = re.compile(rf"^({_QTY})\s+({_FREE})\s+({_NUM})\s+({_NUM})\s*$")

_SKIP_PREFIX = (
    "TOTAL", "GRAND TOTAL", "COMPANY / ITEM", "REPORT FOR", "COMPANY :",
    "CONTINUED", "PAGE NO", "D E S C R I P T I O N", "GSTIN", "PHONE",
    "E-MAIL", "*** END", "FROM ",
)


def parse_company_item_wise_sales_summary(text):
    H = ["Division", "Party Name", "Product Name", "Qty", "Free", "Rate",
         "Amount", "Disc%"]
    lines = text.split("\n")
    letterhead = next((ln.strip() for ln in lines if ln.strip()), "")

    rows, division, party = [], "", ""
    for raw in lines:
        s = raw.strip()
        if not s or set(s) <= set("-"):
            continue
        up = s.upper()
        if up.startswith(_SKIP_PREFIX) or s == letterhead:
            continue
        # party band: leading hyphen followed by a letter (not "-123" numeric)
        if s.startswith("-") and re.match(r"^-\s*[A-Za-z]", s):
            party = s[1:].strip()
            continue
        # product row (six numeric columns)
        m = _ROW.match(s)
        if m:
            free = "0" if m.group(3) == "-" else m.group(3).replace(",", "")
            qty = "0" if m.group(2) == "-" else m.group(2).replace(",", "")
            rows.append([
                division, party, m.group(1).strip(),
                qty, free,
                m.group(4).replace(",", ""),
                m.group(5).replace(",", ""),
                m.group(6).replace(",", ""),
            ])
            continue
        # bare per-party / group subtotal -> skip
        if _SUBTOTAL.match(s):
            continue
        # anything else that is a bare heading with no decimal figure is the
        # COMPANY / DIVISION band (e.g. "KLM (COSMOCOR)", "KLM DERMA").
        if not re.search(r"\d+\.\d", s):
            division = s
    return H, rows
