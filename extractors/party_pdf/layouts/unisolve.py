import re

from extractors.party_pdf.party_area import extract_party_and_area


def parse_unisolve(text):
    H = [
        "Party Name",
        "Area",
        "Product Code",
        "Product Name",
        "Inv Type",
        "Inv No",
        "Date",
        "Batch",
        "Qty",
        "Free",
        "Rate",
        "Value",
        "Prod.Dis",
    ]
    pat = re.compile(
        r"^(\d{7,})\s+(.+?)\s+(INV|DM|INC)\s+(\d+)\s+(\d{2}/\d{2}/\d{2})\s+(\S+)\s+([\d.,]+)\s+(?:([\d.,]+)\s+)?([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)\s*$"
    )
    rows, cur_raw = [], ""
    for line in text.split("\n"):
        s = line.strip()
        cm = re.match(r"^Customer:\s+\[\w+\]\s+(.+)", s)
        if cm:
            cur_raw = cm.group(1).strip()
            continue
        m = pat.match(s)
        if m:
            name, area = extract_party_and_area(cur_raw, "unisolve")
            rows.append(
                [
                    name,
                    area,
                    m.group(1),
                    m.group(2).strip(),
                    m.group(3),
                    m.group(4),
                    m.group(5),
                    m.group(6),
                    m.group(7),
                    m.group(8) or "0",
                    m.group(9),
                    m.group(10),
                    m.group(11),
                ]
            )
    return H, rows
