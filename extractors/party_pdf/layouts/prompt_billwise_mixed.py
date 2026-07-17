import re

from extractors.party_pdf.parse_common import _sk
from extractors.party_pdf.party_area import extract_party_and_area


# --- Prompt ERP "Normal" party-billwise, mixed-case BillRef variant ------------
# Header: "Product Pack BillRef Date MRP Batch Qty Free Rate Amount"
# Party heading precedes each product group: "NAME, TOWN, DISTRICT".
# This is structurally identical to prompt_normal EXCEPT the BillRef token is
# mixed/lower-case with word prefixes and may lack a dash:
#     Cash/1130   Credit-L/196   Credit-O/261
# The rigid prompt_normal regex only accepts ALL-UPPERCASE bill refs
# ([A-Z]+(?:-[A-Z]+)*/\d+) e.g. DB-T/196, M/12, so it yields 0 rows here.
# Broadening to [A-Za-z] on the BillRef token is the only change; the rest of
# the 9-field structure (Product Pack? BillRef Date MRP Batch Qty Free Rate
# Amount) is unchanged. Each captured row reconciles to the vendor's printed
# "Party Total ->" / "Grand Total ->" lines to the paise.
_DATA_PAT = re.compile(
    r"^(.+?)\s+"
    r"([A-Za-z]+(?:-[A-Za-z]+)*/\d+)\s+"          # BillRef: Cash/1130, Credit-L/196
    r"(\d{1,2}[-/]\d{1,2}[-/]\d{4})\s+"           # Date
    r"([\d.]+)\s+"                                # MRP
    r"(\S+)\s+"                                   # Batch
    r"(-?\d+)\s+"                                 # Qty
    r"(\d+)\s+"                                   # Free
    r"([\d.-]+)\s+"                               # Rate
    r"([\d.-]+)\s*$"                              # Amount
)

_SKIP = [
    "Phone",
    "Normal From",
    "Product Pack",
    "Party Total",
    "Grand Total",
    "Page ",
]


def parse_prompt_billwise_mixed(text):
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
    rows, cur_raw = [], ""
    for line in text.split("\n"):
        s = line.strip()
        if not s or _sk(s, _SKIP):
            continue
        m = _DATA_PAT.match(s)
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
            continue
        # Party heading: "NAME, TOWN, DISTRICT" (starts uppercase, comma+cap
        # follows) and is NOT itself a data line.
        if re.match(r"^[A-Z].*,\s*[A-Z]", s):
            cur_raw = s
    return H, rows
