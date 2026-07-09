import re

from extractors.party_pdf.party_area import extract_party_and_area


def parse_marg_bordered(text):
    H = [
        "Party Name",
        "Area",
        "Product Name",
        "Pack",
        "Batch No",
        "MRP",
        "PTR",
        "Pur Rate",
        "Rate",
        "Qty",
        "Free",
        "Claim Qty",
        "Claim Value",
    ]
    pat = re.compile(
        r"^(.+?)\s+(\d[Xx*]\d+\w*)\s+(\w+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+(\d+)\s+(\d+)\s+(\d+)\s+([\d.]+)\s*$"
    )
    rows, cur_raw = [], ""
    for line in text.split("\n"):
        s = line.strip()
        pm = re.match(r"^\([\w*]+\)\s*(.+)", s)
        if pm:
            cur_raw = pm.group(1).strip()
            continue
        m = pat.match(s)
        if m:
            name, area = extract_party_and_area(cur_raw, "marg_bordered")
            rows.append(
                [
                    name,
                    area,
                    m.group(1).strip(),
                    m.group(2),
                    m.group(3),
                    m.group(4),
                    m.group(5),
                    m.group(6),
                    m.group(7),
                    m.group(8),
                    m.group(9),
                    m.group(10),
                    m.group(11),
                ]
            )
    return H, rows
