import re

# "SALE REGISTER CONSOLIDATED" party-itemwise layout (seen from FRIENDS PHARMA /
# GAURAV exports). Header row: "PARTY NAME ITEM NAME QUANTITY FREE AMOUNT" with
# "====" rule separators. Each data row is "<party> ,<area> <item> qty free amount";
# per-party subtotals and the GRAND TOTAL appear as bare/labelled number lines and
# are skipped. The comma between party and area may or may not have a leading space.

_NUM = r"[\d,]+\.\d+"
_ROW = re.compile(rf"^(.+?)\s*,(.+?)\s+({_NUM})\s+({_NUM})\s+({_NUM})\s*$")


def parse_sale_register_consolidated(text):
    H = ["Party Name", "Area", "Product Name", "Qty", "Free", "Amount"]
    rows = []
    for raw in text.split("\n"):
        s = raw.strip()
        if not s or set(s) <= set("="):
            continue
        if s.lower().startswith(("party name", "sale register", "from ", "page", "grand total")):
            continue
        m = _ROW.match(s)
        if not m:
            continue
        party = m.group(1).strip()
        area, _, product = m.group(2).strip().partition(" ")
        product = product.strip()
        if len(party) < 2 or len(product) < 2:
            continue
        rows.append([party, area, product,
                     m.group(3).replace(",", ""), m.group(4).replace(",", ""),
                     m.group(5).replace(",", "")])
    return H, rows
