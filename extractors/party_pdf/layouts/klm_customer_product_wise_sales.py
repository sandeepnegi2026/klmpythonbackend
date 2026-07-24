import re

# INDRA DRUG HOUSE "Customer-ProductWiseSales".
#
# Customer-banded, qty/free/amount (no rate). Structure:
#   Customer-ProductWiseSales(From <d> UpTo <d>)
#   <CUSTOMER NAME> <LOCATION>                      <- party header (location = last token)
#   <DIVISION> ...                                  <- division band (ignored)
#   <PRODUCT (CODE)> <qty> <free> <amount>          <- product row (3 trailing numerics)
#   Total <qty> <free> <amount>                     <- per-party subtotal (oracle)
#   Grand Total <qty> <free> <amount>               <- grand total (oracle)
#
# sum(amount) reconciles EXACTLY to per-party 'Total' + 'Grand Total'.

_NUM = r"-?[\d,]*\.\d+|-?[\d,]+"
_ROW_RE = re.compile(r"^(.*?)\s+(" + _NUM + r")\s+(" + _NUM + r")\s+(" + _NUM + r")\s*$")
_CODE_TAIL = re.compile(r"\(([A-Z0-9][A-Z0-9\-]*)\)\s*$")   # trailing (CODE)


def _peel_code(name):
    return _CODE_TAIL.sub("", name).strip()


def parse_klm_customer_product_wise_sales(text):
    headers = ["Party Name", "Area", "Product Name", "Qty", "Free", "Amount"]
    rows = []
    party = ""
    location = ""
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        up = s.replace(" ", "").upper()
        if up.startswith("CUSTOMER-PRODUCTWISESALES") or re.search(r"PAGE\d+OF\d+", up):
            continue
        m = _ROW_RE.match(s)
        name_up = m.group(1).replace(" ", "").upper() if m else up
        if name_up == "TOTAL" or name_up == "GRANDTOTAL":
            continue                                 # printed oracles (bare keyword only)
        if "DIVISION" in up and m is None:
            continue                                 # division band
        if m:
            rows.append([party, location, _peel_code(m.group(1).strip()),
                         m.group(2), m.group(3), m.group(4)])
        else:
            toks = s.split()
            if len(toks) >= 2:
                location = toks[-1]
                party = _peel_code(" ".join(toks[:-1]))
            else:
                party = _peel_code(s)
                location = ""
    return headers, rows
