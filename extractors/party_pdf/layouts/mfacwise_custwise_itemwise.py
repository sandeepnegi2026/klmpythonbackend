import re

# Business/role words that must never be mistaken for a trailing town on a
# customer heading (guards the town peel below).
_BIZ = {
    "MEDICAL", "MEDICALS", "MEDICOS", "MEDICOSE", "MEDICO", "PHARMA",
    "PHARMACY", "STORE", "STORES", "CHEMIST", "CHEMISTS", "HALL", "CLINIC",
    "HOSPITAL", "SURGICAL", "SURGICALS", "AGENCY", "AGENCIES", "DISTRIBUTORS",
    "ENTERPRISES", "TRADERS", "CO", "COMPANY", "LAB", "GENERAL", "GEN", "AND",
    "CARE", "MART", "HUB", "MEMORIAL",
}

# One numeric-ish token: optional sign, digits, optional decimal.
_NUM = r"-?\d+(?:\.\d+)?"


def _split_heading_town(name):
    """A customer heading is "<PARTY NAME> [<TOWN>]" (the customer code has
    already been stripped). The town, when present, is the LAST token and is an
    ALL-CAPS place word (e.g. "DELITE MEDICALS OLLUR" -> town OLLUR). A trailing
    "**" marker is stripped first. Guarded so a business/role word or a
    too-short / non-alpha token is never peeled into Area."""
    raw = name.strip().rstrip("*").strip()
    parts = raw.rsplit(None, 1)
    if len(parts) < 2:
        return raw, ""
    head, last = parts[0], parts[1]
    town = last.strip(".").strip()
    if (
        not re.fullmatch(r"[A-Za-z][A-Za-z.]*", town)
        or town.upper() in _BIZ
        or len(town) < 3
    ):
        return raw, ""
    return head.strip(), town


def parse_mfacwise_custwise_itemwise(text):
    """BALAJI MEDICAL AGENCIES "Mfacwise Custwise Areawise Itemwise Report".

    Structure (per company band):
      Comapny : <COMPANY>
      <CustCode> <PARTY NAME> [<TOWN>]        <- customer heading (no value cols)
      <ItemCode> <Item Name...> <Area> <Route Name> <Dman Name> \
          <Pack> <Rate> <Qty> <Free> <Amount> <Discount>   <- item row
      Customer wise Total : <amount>
      ...
      Company wise Total : <amount>
      Grand Total: <amount>

    An item row is anchored on its TRAILING 6 numeric tokens
    (Pack Rate Qty Free Amount Discount). Everything before them is
    "<ItemCode> <ItemName> <Area> <Route> <Dman>". Route/Dman render as a
    repeated marker such as "VEHICLE 2 VEHICLE 2" (name + single number, twice),
    so after peeling item code the remaining text splits as:
      Area = leading text, Route/Dman = a trailing "<W> <n> <W> <n>" block.
    The Party Name is carried from the current customer heading; the customer
    heading is the line whose leading token is a numeric code but which carries
    NO trailing numeric value columns.
    """
    headers = [
        "Party Name", "Area", "Item Code", "Product Name",
        "Pack", "Rate", "Qty", "Free", "Amount", "Discount",
    ]

    # An item row ends in exactly six trailing numeric tokens.
    tail6 = re.compile(
        r"^(\S+)\s+(.*?)\s+(" + _NUM + r")\s+(" + _NUM + r")\s+(" + _NUM
        + r")\s+(" + _NUM + r")\s+(" + _NUM + r")\s+(" + _NUM + r")\s*$"
    )
    # A "<Word> <num> <Word> <num>" route/dman block hanging off the end of the
    # middle segment (e.g. "OLLUR VEHICLE 2 VEHICLE 2" or plain "OLLUR VEHICLE 1
    # VEHICLE 1"); the leading remainder is the Area name.
    route_tail = re.compile(
        r"^(.*?)\s+(\S+\s+\d+\s+\S+\s+\d+)\s*$"
    )
    # Customer heading: a numeric customer code then a name, and (crucially) it
    # does NOT end in a numeric value column (that would make it an item row).
    cust_head = re.compile(r"^(\d{4,7})\s+([A-Za-z].*\S)\s*$")

    rows = []
    party = ""
    party_area = ""

    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            continue
        low = s.lower()

        # Structural / non-data lines.
        if (
            low.startswith("comapny")
            or low.startswith("company")            # "Company wise Total :"
            or low.startswith("customer wise total")
            or low.startswith("grand total")
            or low.startswith("mfacwise custwise")
            or low.startswith("code party name")
            or low.startswith("report date")
            or (low.startswith("from ") and " to " in low)
        ):
            continue

        # Item row: anchored on six trailing numbers.
        m = tail6.match(s)
        if m:
            item_code = m.group(1)
            middle = m.group(2).strip()
            pack, rate, qty, free, amount, disc = m.group(3, 4, 5, 6, 7, 8)

            # Peel the trailing "<W> <n> <W> <n>" route/dman block; what remains
            # in front is Item Name + Area. Area is the LAST text token of that
            # remainder (it mirrors the party town, e.g. "...20GM. OLLUR").
            item_name = middle
            area = ""
            rm = route_tail.match(middle)
            if rm:
                pre = rm.group(1).strip()          # "<Item Name> <Area>"
                bits = pre.rsplit(None, 1)
                if len(bits) == 2 and re.search(r"[A-Za-z]", bits[1]):
                    item_name, area = bits[0].strip(), bits[1].strip()
                else:
                    item_name = pre
            rows.append([
                party, area or party_area, item_code, item_name,
                pack, rate, qty, free, amount, disc,
            ])
            continue

        # Customer heading (code + name, no trailing value columns).
        ch = cust_head.match(s)
        if ch:
            party, party_area = _split_heading_town(ch.group(2))
            continue

        # Anything else (blank markers, addresses) — ignore, keep current party.

    return headers, rows
