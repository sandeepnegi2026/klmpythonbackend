import re

from extractors.party_pdf.party_area import extract_party_and_area


def parse_marg_bordered_billwise(text):
    H = [
        "Product Name",
        "Bill No",
        "Bill Date",
        "Party Name",
        "Area",
        "Pack",
        "Batch No",
        "MRP",
        "PTR",
        "Pur Rate",
        "Sales Rate",
        "Qty",
        "Free",
        "Claim Qty",
        "Claim Value",
    ]
    pat = re.compile(
        r"^\s*(\d{5,6})\s+"
        r"(\d{2}/\d{2}/\d{4})\s+"
        r"(.+?)"
        r"(\d+\s*[*]?\s*\d*\s*(?:GM|ML|G\s))"
        r"\s*(?:TUBE\s+)?"
        r"(\S+)\s+"
        r"([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+"
        r"([\d.]+)\s+"
        r"(\d+)\s+(\d+)\s+(\d+)\s+"
        r"([\d.]+)\s*$"
    )
    skip_pf = [
        "Total",
        "Grand",
        "Product",
        "Bill",
        "**",
        "Claim",
        "AARCHI",
        "N.K.",
        "MANISH",
        "SHOP",
        "From",
        "Rate",
        "9825",
        "0261",
        "0433",
        "02612",
        "5-6-7",
        "ROAD,",
        "Qty",
    ]
    rows, prod = [], ""
    for line in text.split("\n"):
        s = line.strip()
        if not s or any(s.startswith(p) for p in skip_pf):
            continue
        m = pat.match(s)
        if m:
            name, area = extract_party_and_area(
                m.group(3).strip(), "marg_bordered_billwise"
            )
            rows.append(
                [
                    prod,
                    m.group(1),
                    m.group(2),
                    name,
                    area,
                    m.group(4).strip(),
                    m.group(5),
                    m.group(6),
                    m.group(7),
                    m.group(8),
                    m.group(9),
                    m.group(10),
                    m.group(11),
                    m.group(12),
                    m.group(13),
                ]
            )
            continue
        if not re.match(r"^\d", s) and not re.match(r"^[a-z]", s):
            pm = re.match(r"^(?:\(\w+\))?(.+?)\.?\s*$", s)
            if pm:
                candidate = pm.group(1).strip()
                if (
                    len(candidate) >= 4
                    and re.search(r"[A-Z]", candidate)
                    and not candidate.startswith("GST")
                    and not candidate.startswith("KL0")
                    and not candidate.startswith("QVQFB")
                    and not candidate.startswith("4UOXD")
                    and ":" not in candidate
                    and "---" not in candidate
                    and not re.match(r"^[A-Z]{2,}\s*:", candidate)
                ):
                    prod = candidate
    return H, rows
