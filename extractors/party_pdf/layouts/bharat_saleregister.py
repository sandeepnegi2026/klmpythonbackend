import re


def parse_bharat_saleregister(text):
    """'SALE REGISTER DETAILED' (BHARAT MEDICAL STORE style). Columns:
    BILL DATE | PARTY NAME | ITEM NAME | TOTAL PACKS | RATE/PACK | NET AMOUNT |
    TOTAL QTY | FREE QTY | RATE/UNIT | TAX. The party name appears (with a
    ' -<area>' suffix) only on the first row of each party block; following rows
    omit it. 'Party Totals' lines delimit blocks.

    NOTE: pdfplumber merges the area into the product on the party-header row,
    so that single first product per party may carry an area prefix; every
    continuation row's product is clean, and Party / Qty / Net-Amount are clean
    on all rows. Qty maps to TOTAL QTY, Amount to NET AMOUNT.

    FREE QTY is an interior column that is BLANK on most rows (collapsing the
    token count) and only prints an integer on rows with free goods; sales
    returns print NEGATIVE packs / amount / qty. The row pattern therefore makes
    the pack/amount/qty signs optional and the FREE QTY integer optional so
    those rows are not dropped (additive; clean rows are unaffected because the
    optional group simply does not fire).
    """
    H = ["Party Name", "Product Name", "Qty", "Amount"]
    rows, party, item = [], "", ""
    ROW = re.compile(
        r"^(.*?)\s+(-?\d+)\s+([\d,]+\.\d+)\s+(-?[\d,]+\.\d+)\s+(-?\d+)"
        r"(?:\s+(\d+))?\s+([\d,]+\.\d+)\s+([\d,]+\.\d+)\s*$"
    )
    # Orphaned continuation row: pdfplumber wraps a long item name up onto the
    # PREVIOUS line, leaving a repeat bill's numeric row with NO item name (and
    # sometimes no date) — "9 138.98 1,446.44 9 138.9800 110.32". Recovering it via
    # the carried item/party recovers the ~7% of qty/amount those wraps otherwise
    # drop (BHARAT reconciles exactly to its printed Grand Total once carried).
    NUMS = re.compile(
        r"^(-?\d+)\s+[\d,]+\.\d+\s+(-?[\d,]+\.\d+)\s+(-?\d+)"
        r"(?:\s+\d+)?\s+[\d,]+\.\d+\s+[\d,]+\.\d+\s*$"
    )
    DATE = re.compile(r"^(\d{2}/\d{2}/\d{4})\s+(.*)$")

    for raw in text.split("\n"):
        s = re.sub(r"\s+", " ", raw.strip())
        if (not s or s.startswith(("Party Totals", "BILL DATE", "Page", "Printed By"))
                or "SALE REGISTER DETAILED" in s):
            continue
        m = ROW.match(s)
        if m:
            prefix = m.group(1).strip()
            net_amt = m.group(4).replace(",", "")   # NET AMOUNT (may be negative)
            total_qty = m.group(5)                  # TOTAL QTY (may be negative)

            d = DATE.match(prefix)
            if d:
                prefix = d.group(2).strip()
            if " -" in prefix:                      # party-header row
                pname, rest = prefix.split(" -", 1)
                party = pname.strip()
                cur = rest.strip()                  # area prefix may remain here
            else:                                   # continuation row (clean item)
                cur = prefix
            if cur:
                item = cur                          # remember the last real item
            if not item:
                continue
            rows.append([party, item, total_qty, net_amt])
            continue
        n = NUMS.match(s)
        if n and item:                              # orphaned numbers-only row
            rows.append([party, item, n.group(3), n.group(2).replace(",", "")])

    return H, rows
