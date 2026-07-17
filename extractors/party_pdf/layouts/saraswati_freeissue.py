import re

from extractors.party_pdf.party_area import extract_party_and_area


def parse_saraswati_freeissue(text):
    headers = ["Party Name", "Area", "Product Name", "Pack", "Inv Type", "Inv No",
               "Date", "Batch", "Qty", "Free", "Rate", "Value",
               "Prod.Dis", "Free Value"]
    rows = []
    cur_product = ""
    cur_pack = ""
    # Product heading: "Product : [10540003] NIOSALIC 6 OINT Pack: 20 GM"
    prod_re = re.compile(r'^Product\s*:\s*\[[^\]]*\]\s*(.+?)\s+Pack:\s*(.+?)\s*$')
    # Data row: CUSTCODE  NAME, ADDRESS  TYPE  NO  DD/MM/YY  BATCH  Qty Free Rate Value Prod.Dis FreeValue
    # Batch may contain an internal space (e.g. "SBP 023"); line may end with a stray ')' page artifact.
    row_re = re.compile(
        r'^([A-Z]\d{3}[A-Z]?)\s+'                       # customer code
        r'(.+?)\s+'                                      # customer name & address
        r'(INV|INC|DM|CRN|CR|SR)\s+'                     # invoice type
        r'(\d+)\s+'                                      # invoice number
        r'(\d{2}/\d{2}/\d{2,4})\s+'                      # date
        r'(.+?)\s+'                                      # batch (may contain a space)
        r'(\d+)\s+(\d+)\s+'                              # qty, free
        r'([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)'     # rate, value, prod.dis, free value
        r'\)?\s*$'                                       # optional trailing page artifact
    )
    for ln in text.splitlines():
        s = ln.strip()
        if not s:
            continue
        m = prod_re.match(s)
        if m:
            cur_product = m.group(1).strip()
            cur_pack = m.group(2).strip()
            continue
        if s.startswith(("Total:", "Total Value", "---", "===", "Product",
                         "Customer Name", "Agency", "SARASWATI")):
            continue
        m = row_re.match(s)
        if m:
            code, name, ityp, ino, date, batch, qty, free, rate, val, pdis, fval = m.groups()
            # "NAME, TOWN" -> split town into Area (same vendor convention as the
            # unisolve sibling report; last comma-segment is the town).
            pname, parea = extract_party_and_area(name.strip(), "unisolve")
            rows.append([pname, parea, cur_product, cur_pack, ityp, ino, date,
                         batch.strip(), qty, free, rate, val, pdis, fval])
    return headers, rows