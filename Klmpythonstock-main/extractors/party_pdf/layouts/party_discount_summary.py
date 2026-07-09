import re

def parse_party_discount_summary(text):
    headers = ["Party Name", "Product Name", "Qty", "Gross Amount", "Item Discount", "Amount"]
    rows = []
    party = None
    num = r"-?\d+(?:\.\d+)?"
    # Detail row: SNo  description  QTY  GROSS  vol1  vol2  ITEMDISC  bill1  bill2  BILLAMT
    # (7 trailing numeric tokens after QTY; QTY is the first integer after the description)
    row_re = re.compile(
        r"^\s*(\d+)\s+(.+?)\s+(\d+)\s+(" + num + r")\s+(" + num + r")\s+(" + num +
        r")\s+(" + num + r")\s+(" + num + r")\s+(" + num + r")\s+(" + num + r")\s*$"
    )
    # Subtotal / pure-numeric line: a sequence of numbers only (no SNo+desc)
    subtotal_re = re.compile(r"^\s*" + num + r"(?:\s+" + num + r")+\s*$")

    for ln in text.split("\n"):
        s = ln.rstrip()
        st = s.strip()
        if not st:
            continue
        # dashed separators
        if set(st) <= set("- "):
            continue
        up = st.upper()
        # header / footer / page furniture
        if up.startswith(("SNO.", "AMOUNT", "PARTY DISCOUNT", "FROM ", "GSTIN", "PHONE",
                          "CONTINUED", "PAGE NO", "GRAND TOTAL", "*** END", "SAM MEDICOS")):
            continue
        if "P A R T Y" in st or "D E S C R I P T I O N" in st:
            continue
        if up.startswith("505/") or "PRAYAGRAJ" in up:
            continue

        m = row_re.match(s)
        if m:
            if party is None:
                continue
            sno, desc, qty, gross, v1, v2, itemdisc, b1, b2, billamt = m.groups()
            rows.append([party, desc.strip(), qty, gross, itemdisc, billamt])
            continue

        # subtotal lines (numbers only) -> skip, do not treat as party
        if subtotal_re.match(s):
            continue

        # anything else at this point is a party heading line
        party = st

    return headers, rows