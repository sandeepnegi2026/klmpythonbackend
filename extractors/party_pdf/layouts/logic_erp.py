import re

from extractors.party_pdf.party_area import extract_party_and_area


def parse_logic_erp(text):
    H = [
        "Party Name",
        "Area",
        "Sr",
        "Code",
        "Product Name",
        "Packing",
        "Batch No.",
        "Qty",
        "FQty",
        "Rate",
        "Amount",
        "Invoice No.",
        "Inv. Date",
    ]
    pat = re.compile(
        r"^(\d+)\s+(\w+)\s+(.+?)\s+(\S+(?:NOS|ML|GM|CAP|TAB|\d+))\s+(\S+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d,.]+)\s+(\S+-\d+-\d+)\s+(\d{2}-\d{2}-\d{4})\s*$"
    )
    rows, cur_raw = [], ""
    for line in text.split("\n"):
        s = line.strip()
        cm = re.match(r"^(?:C\w+|CA\w+|CUS\w+)\s*-\s*(.+)", s)
        if cm:
            cur_raw = cm.group(1).strip()
            continue
        m = pat.match(s)
        if m:
            name, area = extract_party_and_area(cur_raw, "logic_erp")
            rows.append(
                [
                    name,
                    area,
                    m.group(1),
                    m.group(2),
                    m.group(3).strip(),
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
