import re


def parse_prathna_register(text):
    """'Sales Detail Register (Mf-Customerwise)' (PRATHNA-UNITY style). Customer
    names are bare heading lines carrying a comma+area ('ASTAVINAYAK MEDICAL,
    AHMEDABAD NIKOL'); a division/group header ('KLM COSMO-001057 - M00230')
    precedes each customer. Each item row is
    '<srno> <date> <item> <batch> <qty>. <sale-rate>'. The Amount column is
    blank in the extracted text, so Amount is computed as qty x sale-rate
    (this report prints no scheme discount, so that equals the line value).
    """
    H = ["Party Name", "Product Name", "Batch", "Qty", "Rate", "Amount"]
    rows, party = [], ""
    ITEM = re.compile(
        r"^(\w[\w-]*)\s+(\d{2}-\d{2}-\d{4})\s+(.+?)\s+(\S+)\s+(-?\d+)\.\s+([\d,]+\.\d{2})$"
    )
    for raw in text.split("\n"):
        s = re.sub(r"\s+", " ", raw.strip())
        if not s:
            continue

        m = ITEM.match(s)
        if m and party:
            qty = m.group(5)
            rate = float(m.group(6).replace(",", ""))
            try:
                amt = round(int(qty) * rate, 2)
            except ValueError:
                amt = ""
            rows.append([
                party,
                m.group(3).strip(),
                m.group(4),
                qty,
                m.group(6).replace(",", ""),
                amt,
            ])
            continue

        # group / division header e.g. 'KLM COSMO-001057 - M00230' -> not a party
        if s.startswith("KLM ") or re.search(r"-\S+\s+-\s+\w+$", s):
            continue
        # report chrome
        su = s.upper()
        if ("SALES DETAIL" in su or su.startswith(("SRNO", "PAGE", "FROM "))
                or "PHARMA LLP" in su or set(s) <= set("-")):
            continue
        # subtotal lines start with a number ('2. 0. 0.00')
        if re.match(r"^[\d.]", s):
            continue
        # a customer heading (store name + ', area') becomes the current party
        if "," in s and re.search(r"[A-Za-z]", s):
            party = s

    return H, rows
