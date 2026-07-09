import re

from extractors.party_pdf.party_area import extract_party_and_area


def parse_wep_legacy(text):
    text = re.sub(r"\(cid:\d+\)", "", text)
    H = [
        "Party Name",
        "Area",
        "Product Code",
        "Product Name",
        "Qty",
        "Free Qty",
        "Goods Value",
        "PRate",
        "Value(PRate)",
    ]
    pat = re.compile(
        r"^(\d+)\s+(.+?)\s+(\d+)\s+(\d+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*$"
    )
    rows, cur_raw = [], ""
    for line in text.split("\n"):
        s = line.strip().rstrip("*'").strip()
        cm = re.match(r"^CUSTOMER NAME\s*:\s*(.+)", s)
        if cm:
            cur_raw = cm.group(1).strip()
            continue
        m = pat.match(s)
        if m:
            name, area = extract_party_and_area(cur_raw, "wep_legacy")
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
                ]
            )
    return H, rows
