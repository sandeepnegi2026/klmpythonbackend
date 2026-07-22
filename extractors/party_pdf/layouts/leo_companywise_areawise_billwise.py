import re

# LEO PHARMA DISTRIBUTORS "Companywise Areawise Report" (billwise).
#
# Party-banded billwise. Structure:
#   LEO PHARMA DISTRIBUTORS ... / Companywise Areawise Report From <d> To <d>
#   BILLNO DATE ITEMNAME BATCHNO EXP QTY FREE TD SRATE TOTAL      <- header
#   KLM LABORATORIES PVT LTD                                       <- company band (ignored)
#   <PARTY NAME> - <AREA>                                          <- party header (split last ' - ')
#   <LP[HS]/n/n> <date> <ITEMNAME...> <BATCH> <EXP> <QTY> <FREE> <TD> <SRATE> <TOTAL>
#   ...
#   Customer Total <amount>                                        <- per-party oracle
#   Company Total <amount>                                         <- grand oracle
#
# The bill row's TOTAL (last token) is the sale amount; sum reconciles EXACTLY to
# per-party 'Customer Total' + 'Company Total'. TD column (toks[-3]) is always '-'.

_BILL_RE = re.compile(r"^LP[HS]/\d+/\d+\s")


def _to_num(tok):
    return "0" if tok == "-" else tok.replace(",", "")


def _is_company_header(line):
    return bool(re.search(r"\b(PVT|LTD|LABORATORIES|LIMITED)\b", line)) and not _BILL_RE.match(line)


def parse_leo_companywise_areawise_billwise(text):
    headers = ["Party Name", "Area", "Product Name", "Invoice No",
               "Invoice Date", "Qty", "Free", "Rate", "Amount"]
    rows = []
    cur_party = ""
    cur_area = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if (line.startswith("LEO PHARMA DISTRIBUTORS")
                or line.startswith("Companywise Areawise Report")
                or line.startswith("BILLNO DATE ITEMNAME")
                or line.startswith("Customer Total") or line.startswith("Company Total")
                or re.match(r"^\d{2}-\d{2}-\d{4}\s+\d{2}:\d{2}:\d{2}$", line)):
            continue
        if _BILL_RE.match(line):
            toks = line.split()
            rows.append([cur_party, cur_area, " ".join(toks[2:-5]), toks[0], toks[1],
                         _to_num(toks[-5]), _to_num(toks[-4]), _to_num(toks[-2]),
                         _to_num(toks[-1])])
            continue
        if _is_company_header(line):
            continue
        # party header "PARTY NAME - AREA" (split on LAST ' - ')
        if " - " in line:
            cur_party, cur_area = [s.strip() for s in line.rsplit(" - ", 1)]
        else:
            cur_party, cur_area = line.strip(), ""
    return headers, rows
