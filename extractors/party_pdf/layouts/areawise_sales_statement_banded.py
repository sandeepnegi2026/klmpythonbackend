import re

# ---------------------------------------------------------------------------
# CENTRAL AGENCIES (Calicut) "Areawise Sales Statement" — AREA-BANDED variant
# (KLM COSMO, BlueFox Systems export).  Sibling of the SwilERP
# `areawise_sales_statement` / `areawise_sales_statement_packing` layouts, but a
# STRUCTURALLY DIFFERENT export:
#
#   * NO "Location :" markers and NO "Code / Customer Name / Rep Code" columns;
#     instead the body is banded twice — first by AREA, then by CUSTOMER:
#         <AREA band>          -> "<AREA name> <area subtotal amount>"
#         <CUSTOMER sub-band>  -> "<party name, address...> <party subtotal>"
#         <detail rows>        -> "<BillNo> <dd/mm/yyyy> <Product...> <Pack>
#                                  <Qty> <Free> <Amount>"
#   * the column header is:
#         "Bill No Bill Date Product Name Packing Qty Free Qty Amount"
#     (there is no customer-code / rep-code column at all).
#
# Detail row (single space-delimited text line):
#   <BillNo:int> <dd/mm/yyyy> <Product Name ... Packing> <Qty:int> <Free:int>
#   <Amount:money>
# The Packing prints inline as the tail of the product name (e.g. "30ML",
# "50gm", "60ML", "100gm"); there is no separate positional Packing value, so
# product+pack is captured together as the product name.  Qty/Free/Amount are
# the trailing "int int money" triple.
#
# Band disambiguation (anchored, NOT positional):
#   * a DETAIL row starts with "<digits> <dd/mm/yyyy>";
#   * every BAND line is "<text ...> <trailing money>" with NO leading
#     billno/date.  Among bands, the CUSTOMER sub-band ALWAYS contains a comma
#     (business name + address/town, e.g. "C.H MEDICALS, KOYILANDY"), while the
#     AREA band is a bare ALL-CAPS location code with NO comma
#     ("CLT CITY", "ALLEPEY-KOT-TVM", "KOYILANDY / MELADY").
#
# party_name = most recent CUSTOMER sub-band (comma peeled to the business name);
# area       = most recent AREA band.
#
# Reconciles EXACTLY: summed Amount == printed "Grand Total :" (17232.95) and
# each customer sub-band subtotal == the sum of its own detail rows.
# ---------------------------------------------------------------------------

H = ['Party Name', 'Area', 'Product Name', 'Bill No', 'Bill Date',
     'Qty', 'Free', 'Amount']

# Detail row: BillNo, dd/mm/yyyy, Product(+pack), Qty, Free, Amount.
_ROW = re.compile(
    r'^(\d+)\s+'                    # 1 Bill No
    r'(\d{2}/\d{2}/\d{4})\s+'       # 2 Bill Date
    r'(.*?)\s+'                     # 3 Product Name (pack printed inline)
    r'(\d+)\s+'                     # 4 Qty
    r'(\d+)\s+'                     # 5 Free
    r'([\d,]+\.\d+)\s*$'            # 6 Amount
)

# Band line: "<text> <trailing money>" with no leading billno/date.
_BAND = re.compile(r'^(.*\S)\s+([\d,]+\.\d+)\s*$')


def parse_areawise_sales_statement_banded(text):
    rows = []
    area = ''
    party = ''
    for ln in text.splitlines():
        s = ln.strip()
        if not s:
            continue

        # Detail rows first (anchored by "<digits> <dd/mm/yyyy>").
        m = _ROW.match(s)
        if m:
            billno, date, prod, qty, free, amt = m.groups()
            rows.append([
                party, area, prod.strip(), billno, date,
                qty, free, amt.replace(',', ''),
            ])
            continue

        # Band lines carry a trailing subtotal amount but no bill-no/date.
        b = _BAND.match(s)
        if b:
            label = b.group(1).strip()
            if _is_furniture(label):
                continue
            if ',' in label:
                # CUSTOMER sub-band: business name + address/town.
                party = _clean_party(label)
            else:
                # AREA band: bare all-caps location code (no comma).
                area = label
            continue
    return H, rows


def _clean_party(label):
    """The customer sub-band prints "<business name>, <address/town...>"; the
    area is captured separately from the AREA band, so peel everything from the
    FIRST comma onward to leave a clean business name.  Shelf/rack markers the
    vendor glues to some names ("*---A", "--45 D", "85-F*") are part of how the
    vendor identifies the customer and are left intact."""
    return label.split(',', 1)[0].strip()


def _is_furniture(label):
    """Skip roll-up / footer lines that also end in a trailing money token
    ("Grand Total : 17232.95")."""
    low = label.lower()
    return low.startswith('grand total') or low.endswith('grand total :') \
        or 'grand total' in low
