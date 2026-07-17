import re

from extractors.party_pdf.parse_common import _sk
from extractors.party_pdf.party_area import extract_party_and_area


def parse_marg_summary(text):
    H = [
        "Party Name",
        "Area",
        "Item Name",
        "Item Code",
        "Qty",
        "Sch Qty",
        "Sale Amount",
        "MRP Amt",
        "Pur Amt",
    ]
    pat = re.compile(
        r"^(.+?)\s+((?:\d{6}|PM\d{4}))\s+(\d+)\s+(\d+)\s+([\d.]+)(?:\s+([\d.]+))?(?:\s+([\d.]+))?\s*$"
    )
    rows, cur_raw = [], ""
    for line in text.split("\n"):
        s = line.strip()
        if not s:
            continue
        m = pat.match(s)
        if m:
            name, area = extract_party_and_area(cur_raw, "marg_summary")
            rows.append(
                [
                    name,
                    area,
                    m.group(1).strip(),
                    m.group(2),
                    m.group(3),
                    m.group(4),
                    m.group(5),
                    m.group(6) or "",
                    m.group(7) or "",
                ]
            )
        elif re.match(r"^\d+\s+\d+\s+[\d.]+", s):
            pass
        elif re.match(r"^[A-Z\d].*[A-Za-z]", s) and not _sk(
            s,
            [
                "KLM",
                "Sales",
                "Item",
                "Report",
                "Page",
                "Amount",
                "SOURABH",
                "DAHOD",
                "5,",
                "MF",
                "1ST",
            ],
        ):
            cm = re.match(r"^\d+\s+(.+)", s)
            cur_raw = cm.group(1).strip() if cm else s
    return H, rows
