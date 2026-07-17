import re

from extractors.party_pdf.parse_common import _sk
from extractors.party_pdf.party_area import extract_party_and_area


def parse_marg_sale_details(text):
    H = ["Product Name", "Party Name", "Area", "Qty", "Free", "Amount", "GST Amount", "Net Amt"]
    pat = re.compile(
        r"^(.+?)\s+(\d+)\s+(?:(\d+)\s+)?([\d,]+\.\d+)\s+([\d,]+\.\d+)\s+([\d,]+\.\d+)\s*$"
    )
    rows, prod = [], ""
    for line in text.split("\n"):
        s = line.strip()
        if not s:
            continue
        m = pat.match(s)
        if m and len(m.group(1)) > 3 and not m.group(1).strip().isdigit():
            name, area = extract_party_and_area(m.group(1).strip(), "marg_sale_details")
            rows.append(
                [
                    prod,
                    name,
                    area,
                    m.group(2),
                    m.group(3) or "0",
                    m.group(4),
                    m.group(5),
                    m.group(6),
                ]
            )
        elif re.match(r"^\d+\s+(?:\d+\s+)?[\d,]+\.\d+", s):
            pass
        elif (
            re.match(r"^[A-Z]", s)
            and not re.search(r"\d{2}\.\d{2}", s)
            and not _sk(s, ["TIRUPATI", "SALE ", "QTY", "RAJNANDGAON"])
        ):
            prod = s
    return H, rows
