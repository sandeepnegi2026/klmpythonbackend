import re

# ATTASSERIL PHARMA LINK "Partywise Qtywise Sales".
#
# Party-banded, qty+amount (no rate). Structure:
#   Attasseril Pharma Link / Partywise Qtywise Sales from <d> to <d>
#   <PartyCode> <NAME> (<phone>), <AREA>            <- party header (code = A-Z + 2-4 digits)
#   KLM <division>                                  <- division label (ignored)
#   <serial> <itemcode> <PRODUCT...> <qty> <free> <amount>
#   ...
#   Total <amount>                                  <- per-party subtotal (oracle)
#   G.Tot <amount>                                  <- grand total (oracle)
#
# sum(amount) reconciles EXACTLY to per-party 'Total' + grand 'G.Tot'.

_PARTY_RE = re.compile(r"^([A-Z]\d{2,4})\s+(.*)$")
_AMOUNT_RE = re.compile(r"^\d+\.\d{2}$")
_SKIP_PREFIX = ("Attasseril Pharma Link", "Partywise Qtywise Sales", "Route :", "Contd")


def parse_klm_partywise_qtywise_sales(text):
    headers = ["Party Name", "Area", "Product Name", "Qty", "Free", "Amount"]
    rows = []
    cur_party = ""
    cur_area = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(_SKIP_PREFIX):
            continue
        if line.startswith("G.Tot") or line.startswith("Total"):
            continue
        toks = line.split()
        # product row: serial int + item-code int + trailing 2dp amount, >=5 tokens
        if (toks and toks[0].isdigit() and len(toks) >= 5
                and toks[1].isdigit() and _AMOUNT_RE.match(toks[-1])):
            rows.append([cur_party, cur_area, " ".join(toks[2:-3]),
                         toks[-3], toks[-2], toks[-1]])
            continue
        m = _PARTY_RE.match(line)
        if m and ("," in line or "(" in line):
            rest = m.group(2)
            if "," in rest:
                namepart, area = rest.rsplit(",", 1)
                cur_area = area.strip()
            else:
                namepart, cur_area = rest, ""
            # drop a trailing (phone) and any trailing +/-/= sign
            namepart = re.sub(r"\s*\([^)]*\)\s*$", "", namepart)
            cur_party = re.sub(r"\s*[\+\-\=]\s*$", "", namepart).strip()
            continue
        # else: 'KLM ...' division/company label -> ignore
    return headers, rows
