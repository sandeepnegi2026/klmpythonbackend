import re


def parse_bharat_saleregister(text):
    """'SALE REGISTER DETAILED' (BHARAT MEDICAL STORE style). Columns:
    BILL DATE | PARTY NAME | ITEM NAME | TOTAL PACKS | RATE/PACK | NET AMOUNT |
    TOTAL QTY | RATE/UNIT | TAX. The party name appears (with a ' -<area>'
    suffix) only on the first row of each party block; following rows omit it.
    'Party Totals' lines delimit blocks.

    NOTE: pdfplumber merges the area into the product on the party-header row,
    so that single first product per party may carry an area prefix; every
    continuation row's product is clean, and Party / Qty / Net-Amount are clean
    on all rows. Qty maps to TOTAL QTY, Amount to NET AMOUNT.
    """
    H = ["Party Name", "Product Name", "Qty", "Amount"]
    rows, party = [], ""
    ROW = re.compile(
        r"^(.*?)\s+(\d+)\s+([\d,]+\.\d+)\s+([\d,]+\.\d+)\s+(\d+)\s+"
        r"([\d,]+\.\d+)\s+([\d,]+\.\d+)\s*$"
    )
    DATE = re.compile(r"^(\d{2}/\d{2}/\d{4})\s+(.*)$")

    for raw in text.split("\n"):
        s = re.sub(r"\s+", " ", raw.strip())
        if not s or s.startswith(("Party Totals", "BILL DATE", "Page", "Printed By")):
            continue
        m = ROW.match(s)
        if not m:
            continue
        prefix = m.group(1).strip()
        net_amt = m.group(4).replace(",", "")
        total_qty = m.group(5)

        d = DATE.match(prefix)
        if d:
            prefix = d.group(2).strip()
        if " -" in prefix:                      # party-header row
            pname, rest = prefix.split(" -", 1)
            party = pname.strip()
            item = rest.strip()                 # area prefix may remain here
        else:                                   # continuation row (clean item)
            item = prefix
        if not item:
            continue
        rows.append([party, item, total_qty, net_amt])

    return H, rows
