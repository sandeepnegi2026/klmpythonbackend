import re

from extractors.party_pdf.parse_common import _sk
from extractors.party_pdf.party_area import extract_party_and_area


def parse_technomax_free_qty(text):
    H = [
        "Party Name",
        "Area",
        "Product Code",
        "Product Name",
        "Batch",
        "Inv No",
        "Date",
        "MRP",
        "Rate",
        "Qty",
        "Free Qty",
        "Free Value",
    ]
    pat = re.compile(
        r"^(\d{5,6})\s+(.+?)\s+(\S+)\s+(\S+)\s+(\d{2}-\d{2}-\d{4})\s+"
        r"([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+(\d+)\s+(\d+)\s+(\d+)\s+([\d.]+)\s*$"
    )
    rows, cur_raw = [], []
    skip_pf = [
        "Year :",
        "Free Quantity Statement",
        "Code Product",
        "KLM LABORATORIES",
        "MANISH",
        "Contact:",
        "Email:",
        "Page ",
    ]
    for line in text.split("\n"):
        s = line.strip()
        if not s or _sk(s, skip_pf):
            continue
        pm = re.match(r"^([A-Z0-9]{2,6}\d{0,3})\s*-\s*(.+)$", s)
        if pm and not pat.match(s):
            cur_raw = pm.group(2).strip()
            continue
        m = pat.match(s)
        if m:
            name, area = extract_party_and_area(cur_raw, "technomax_free_qty")
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
                    m.group(9),
                    m.group(10),
                    m.group(11),
                    m.group(12),
                ]
            )
    return H, rows
