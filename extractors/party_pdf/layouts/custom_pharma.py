import re

from extractors.party_pdf.party_area import extract_party_and_area


def parse_custom_pharma(text):
    H = [
        "Party Name",
        "Area",
        "Product Name",
        "Bill Ref",
        "Date",
        "MRP",
        "Batch",
        "Qty",
        "Free",
        "Rate",
        "Amount",
    ]
    pat = re.compile(
        r"^(.+?)\s+(DB-T/\d+)\s+(\d{2}/\d{2}/\d{4})\s+([\d.]+)\s+(\S+)\s+(\d+)\s+(\d+)\s+([\d.]+)\s+([\d.]+)\s*$"
    )
    rows, cur_raw = [], ""
    for line in text.split("\n"):
        s = line.strip()
        if re.match(r"^[A-Z][A-Z\s&.,()\[\]/-]+,\s*[A-Z]", s) and "DB-T/" not in s:
            cur_raw = s
            continue
        m = pat.match(s)
        if m:
            name, area = extract_party_and_area(cur_raw, "custom_pharma")
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
                ]
            )
    return H, rows
