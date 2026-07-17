import re

# ---------------------------------------------------------------------------
# CENTRAL AGENCIES (Calicut) "Areawise Sales Statment" — KLM sub-stockist,
# one file per KLM division (COSMO / COSMOQ / DERMA / DERMACOR / PEDIA / ...).
#
# Report furniture:
#   CENTRAL AGENCIES / <address> / "Areawise Sales Statment from May/2026 ..." /
#   Division / Product Group / Product / Representative / Exported Date /
#   column header "BillNo Bill Date Code Customer Name Rep Code Product Name
#   Packing Qty Free Qty Amount".
#
# Body = "Location : <AREA> (N item[s])" band -> item rows -> a bare per-band
# subtotal (money on its own line) -> ... -> a final bare grand-total line.
#
# Item row (single text line, space-delimited):
#   <BillNo> <dd/mm/yyyy> <CustCode 6d> <Customer Name...> <Rep Code>
#   <Product Code 6d+> <Product Name...> <Qty:int> <Free:int> <Amount:money>
# where Rep Code is a 1-2 digit rep, optionally " DISC" (a discount scheme tag).
# The pack ("50gm"/"100ML") prints inline as the tail of the product name; there
# is no separate Packing value. Disambiguation is anchored, NOT positional:
#   * the Rep Code is the FIRST "\d{1,2}( DISC)?" that is immediately followed by
#     a >=6-digit product code -- so embedded shelf codes like "----10 D" or a
#     "1.25 LT" pack in the customer name (2 digits NOT followed by a 6+ code)
#     never get mistaken for it;
#   * qty/free/amount are the trailing "int int money" triple.
#
# Reconciles EXACTLY: summed Amount == the printed grand-total line on every
# reference file (klm cosmo 12898.735, derma 11578.693, dermacore 25308.675,
# peadi 1755.855, peadia 2076.461, cosmoq 22719.247).
# ---------------------------------------------------------------------------

H = ['Party Name', 'Area', 'Product Name', 'Bill No', 'Bill Date',
     'Qty', 'Free', 'Amount']

_LOC = re.compile(r'^Location\s*:\s*(.+?)(?:\s*\(\d+\s+items?\))?\s*$', re.I)

_ROW = re.compile(
    r'^(\d+)\s+'                    # 1 BillNo
    r'(\d{2}/\d{2}/\d{4})\s+'       # 2 Bill Date
    r'(\d{4,7})\s+'                 # 3 Customer Code
    r'(.*?)\s+'                     # 4 Customer Name (non-greedy)
    r'(\d{1,2}(?:\s+DISC)?)\s+'     # 5 Rep Code  (e.g. "10 DISC", "07")
    r'(\d{6,})\s+'                  # 6 Product Code (anchors the split)
    r'(.*?)\s+'                     # 7 Product Name (pack printed inline)
    r'(\d+)\s+'                     # 8 Qty
    r'(\d+)\s+'                     # 9 Free
    r'([\d,]+\.\d+)\s*$'            # 10 Amount
)


def parse_areawise_sales_statement(text):
    rows = []
    area = ''
    for ln in text.splitlines():
        s = ln.strip()
        if not s:
            continue
        loc = _LOC.match(s)
        if loc:
            area = loc.group(1).strip()
            continue
        m = _ROW.match(s)
        if m:
            billno, date, _code, cust, _rep, _pcode, prod, qty, free, amt = m.groups()
            rows.append([
                _clean_party(cust), area, prod.strip(), billno, date,
                qty, free, amt.replace(',', ''),
            ])
    return H, rows


def _clean_party(cust):
    """The customer field prints "<business name>, <town>[, <sub-town>]" (e.g.
    "BUDGET PHARMA CARE -MOTHER LLP, CHALAPPURAM"). The area/town is already
    captured from the "Location :" band, so peel everything from the FIRST comma
    onward to leave a clean party name; the shelf/rack code the vendor glues to
    some names ("----10 D", "-----B", "[1]") is left intact as it is part of how
    the vendor identifies the customer."""
    name = cust.strip()
    if ',' in name:
        name = name.split(',', 1)[0].strip()
    return name
