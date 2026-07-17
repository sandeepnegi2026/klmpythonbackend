import re

# "SALE REGISTER CONSOLIDATED" party-itemwise layout (seen from FRIENDS PHARMA /
# GAURAV exports). Header row: "PARTY NAME ITEM NAME QUANTITY FREE AMOUNT" with
# "====" rule separators. Each data row is "<party> ,<area> <item> qty free amount";
# per-party subtotals and the GRAND TOTAL appear as bare/labelled number lines and
# are skipped. The comma between party and area may or may not have a leading space.

_NUM = r"[\d,]+\.\d+"
_ROW = re.compile(rf"^(.+?)\s*,(.+?)\s+({_NUM})\s+({_NUM})\s+({_NUM})\s*$")
# KHATTAR variant: extra AVG.RATE column -> 4 numbers (qty, free, rate, amount), and the
# qty/free may print as integers, so allow an optional decimal.
_NUM2 = r"[\d,]+(?:\.\d+)?"
_ROW4 = re.compile(rf"^(.+?)\s*,(.+?)\s+({_NUM2})\s+({_NUM2})\s+({_NUM2})\s+({_NUM2})\s*$")


def parse_sale_register_consolidated(text):
    avg_rate = "avg.rate" in text.lower() or "avg. rate" in text.lower()
    if avg_rate:
        H = ["Party Name", "Area", "Product Name", "Qty", "Free", "Rate", "Amount"]
        row_re = _ROW4
    else:
        H = ["Party Name", "Area", "Product Name", "Qty", "Free", "Amount"]
        row_re = _ROW
    rows = []
    for raw in text.split("\n"):
        s = raw.strip()
        if not s or set(s) <= set("="):
            continue
        if s.lower().startswith(("party name", "sale register", "from ", "page", "grand total")):
            continue
        m = row_re.match(s)
        if not m:
            continue
        party = m.group(1).strip()
        area, _, product = m.group(2).strip().partition(" ")
        product = product.strip()
        if len(party) < 2 or len(product) < 2:
            continue
        nums = [g.replace(",", "") for g in m.groups()[2:]]
        rows.append([party, area, product] + nums)
    return H, rows
