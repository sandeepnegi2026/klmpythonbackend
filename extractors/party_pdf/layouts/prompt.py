import re

from extractors.party_pdf.parse_common import _sk
from extractors.party_pdf.party_area import extract_party_and_area


def _is_prompt_party_line(s):
    if "M/" in s or "Total" in s:
        return False
    if not re.match(r"^[A-Z].*,", s):
        return False
    return bool(
        re.search(
            r"\b(MEDICAL|MEDICO|CHEMIST|PHARMACY|PHARMA|STORE|CLINIC|HOSPITAL|DR\.? )\b",
            s,
            re.I,
        )
    )


def parse_prompt_free_qty(text):
    H = [
        "Party Name",
        "Area",
        "Product Name",
        "Bill Ref",
        "Date",
        "Qty",
        "Free",
        "Rate",
        "Amount",
    ]
    rows, cur_party, cur_product = [], [], []
    data_pat = re.compile(
        r"^(M/\d+)\s+(\d{1,2}/\d{1,2}/\d{4})\s+(\d+)\s+([\d.]+)\s+([\d.]+)\s*$"
    )
    skip_pf = [
        "Phone",
        "Free Quantity",
        "ProductName",
        "Product Total",
        "Party Total",
        "From:",
        "GF PAVANDHAM",
        "Vadodara",
    ]
    for line in text.split("\n"):
        s = line.strip()
        if not s or _sk(s, skip_pf):
            continue
        m = data_pat.match(s)
        if m and cur_party and cur_product:
            name, area = extract_party_and_area(cur_party, "marg_summary")
            rows.append(
                [
                    name,
                    area,
                    cur_product,
                    m.group(1),
                    m.group(2),
                    "0",        # Qty
                    m.group(3), # Free
                    m.group(4), # Rate
                    m.group(5), # Amount
                ]
            )
            continue
        if _is_prompt_party_line(s):
            cur_party = s
            cur_product = ""
            continue
        if "Total" in s:
            continue
        if "M/" not in s and not re.search(r"\d{1,2}/\d{1,2}/\d{4}", s):
            cur_product = s.split(",")[0].strip() if "," in s else s
    return H, rows


def parse_prompt_normal(text):
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
    # Bill ref: any letter-group(s) joined by dashes then '/digits' (DB-T/, M/,
    # DB-SR-T/, CA-T/, GCN-D/ ...). Date: dd-mm-yyyy or dd/mm/yyyy. Broadening
    # these two only ADDS matches inside the otherwise-rigid 9-field structure;
    # the original DB-T/M/DB-SR-T + slash-date inputs still match unchanged.
    pat = re.compile(
        r"^(.+?)\s+([A-Z]+(?:-[A-Z]+)*/\d+)\s+(\d{1,2}[-/]\d{1,2}[-/]\d{4})\s+([\d.]+)\s+(\S+)\s+(-?\d+)\s+(\d+)\s+([\d.-]+)\s+([\d.-]+)\s*$"
    )
    rows, cur_raw = [], []
    skip_pf = [
        "Phone",
        "Normal From",
        "Product Pack",
        "Party Total",
        "CHIRAG",
        "1 ST FLOOR",
        "BILIMORA",
    ]
    for line in text.split("\n"):
        s = line.strip()
        if not s or _sk(s, skip_pf):
            continue
        if (
            re.match(r"^[A-Z].*,\s*[A-Z]", s)
            and not pat.match(s)
            and "DB-T/" not in s
            and "DB-SR-T/" not in s
        ):
            cur_raw = s
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
                    m.group(6),
                    m.group(7),
                    m.group(8),
                    m.group(9),
                ]
            )
    return H, rows
