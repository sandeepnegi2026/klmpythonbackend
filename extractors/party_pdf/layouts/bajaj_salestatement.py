import re


def parse_bajaj_salestatement(text):
    """'SALES STATEMENT' (BAJAJ CHEMIST style). Each bill is a header line
    '<bill-no> <party name> <amount> <disc> <net> <tax> <payable> <running-bal>'
    followed by one or more product detail lines
    '<product> <batch> <qty> <amount> <disc> <net> <tax> <rate/unit>'.
    A bare date line ('01-05-2026') precedes a day's bills. The party comes
    from the bill header; each detail line emits one row carrying that party.
    """
    H = ["Party Name", "Product Name", "Batch", "Qty", "Rate", "Amount"]
    rows, party = [], ""

    NUM = r"-?[\d,]+\.\d{2}"
    # Bill header: bill-no + party + exactly 6 money columns
    BILL = re.compile(
        r"^(B\d+)\s+(.+?)\s+" + NUM + r"\s+" + NUM + r"\s+" + NUM
        + r"\s+" + NUM + r"\s+" + NUM + r"\s+" + NUM + r"$"
    )
    # Detail: product + batch + qty(int) + amount + disc + net + tax + rate
    DETAIL = re.compile(
        r"^(?P<prod>.+?)\s+(?P<batch>\S+)\s+(?P<qty>-?\d+)\s+"
        r"(?P<amt>" + NUM + r")\s+" + NUM + r"\s+" + NUM + r"\s+" + NUM
        + r"\s+(?P<rate>" + NUM + r")$"
    )

    for raw in text.split("\n"):
        s = re.sub(r"\s+", " ", raw.strip())
        if not s or set(s) <= set("-"):
            continue
        su = s.upper()
        if su.startswith(("BILL NO", "COMPANY", "GSTIN", "PHONE", "SALES STATEMENT",
                          "GRAND", "TOTAL", "PAGE", "----")) or "E-MAIL" in su:
            continue

        mb = BILL.match(s)
        if mb:
            party = mb.group(2).strip()
            continue

        md = DETAIL.match(s)
        if md and party:
            rows.append([
                party,
                md.group("prod").strip(),
                md.group("batch"),
                md.group("qty"),
                md.group("rate").replace(",", ""),
                md.group("amt").replace(",", ""),
            ])

    return H, rows
