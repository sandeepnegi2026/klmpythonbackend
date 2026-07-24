import re

# ---------------------------------------------------------------------------
# CENTRAL DISTRIBUTORS (Kasaragod) "Areawise Sales Statment on <Mon>/<YYYY>" —
# KLM sub-stockist, one file per KLM division (COSMO / DERMA / ...).  This is a
# sibling of `areawise_sales_statement` (CENTRAL AGENCIES, Calicut) but a
# DIFFERENT variant of the same SwilERP export:
#
#   * the column header carries an explicit "Packing" column:
#       "BillNo Bill Date Code Customer Name Rep Code Product Name Packing
#        Qty Free Qty Amount"
#     (the CENTRAL AGENCIES variant has NO Packing column);
#   * the Rep Code is an ALPHABETIC representative *name*
#     (ACCREDO / SURENDRAN PV / DIRECT), not a 1-2 digit numeric rep;
#   * the Product Code is 4-5 digits (not necessarily >=6);
#   * the Packing value prints as its own token ("10's" / "60ml" / "3's")
#     between the product name and the trailing Qty/Free/Amount triple.
#
# Body = "Location : <AREA> (N item[s])" band -> item rows -> a bare per-band
# subtotal (money on its own line) -> ... -> a final bare grand-total line.
#
# Item row (single text line, space-delimited):
#   <BillNo> <dd/mm/yyyy> <CustCode 4-7d> <Customer Name...,town...>
#   <Rep Name UPPER> <Product Code 4+d> <Product Name...> <Packing>
#   <Qty:int> <Free:int> <Amount:money>
#
# Disambiguation is anchored, NOT positional: the split point is the >=4-digit
# product code that immediately follows the UPPERCASE rep name.  Qty/Free/Amount
# are the trailing "int int money" triple; the token before Qty is the Packing.
#
# Reconciles EXACTLY: summed Amount == the printed grand-total line
# (COSMO/KLMA.pdf: 36570.788).
# ---------------------------------------------------------------------------

H = ['Party Name', 'Area', 'Product Name', 'Bill No', 'Bill Date',
     'Qty', 'Free', 'Amount']

_LOC = re.compile(r'^Location\s*:\s*(.+?)(?:\s*\(\d+\s+items?\))?\s*$', re.I)

_ROW = re.compile(
    r'^(\d+)\s+'                       # 1 BillNo
    r'(\d{2}/\d{2}/\d{4})\s+'          # 2 Bill Date
    r'(\d{4,7})\s+'                    # 3 Customer Code
    r'(.*?)\s+'                        # 4 Customer Name (non-greedy, incl town)
    r'([A-Z][A-Z. ]*?)\s+'            # 5 Rep Name (UPPER, e.g. "SURENDRAN PV")
    r'(\d{4,})\s+'                     # 6 Product Code (anchors the split)
    r'(.*?)\s+'                        # 7 Product Name (non-greedy)
    r'(\S+)\s+'                        # 8 Packing (e.g. "10's", "60ml")
    r'(\d+)\s+'                        # 9 Qty
    r'(\d+)\s+'                        # 10 Free
    r'([\d,]+\.\d+)\s*$'               # 11 Amount
)

# Same layout, but the Rep column is a bare NUMERIC rep code (CENTRAL AGENCIES
# Calicut prints "07"/"01"/"10" here, not an alpha rep name), so _ROW's uppercase
# rep group can't match and the row is silently dropped. This variant matches the
# numeric rep and is tried ONLY as a fallback when _ROW fails, so every row _ROW
# already parses (alpha reps like "DISC", the Kasaragod KLMA reference file) stays
# byte-identical — this can only RECOVER currently-dropped rows. The product code
# (>=4 digits) still anchors the product/pack split, so names stay clean.
_ROW_NUMREP = re.compile(
    r'^(\d+)\s+'                       # 1 BillNo
    r'(\d{2}/\d{2}/\d{4})\s+'          # 2 Bill Date
    r'(\d{4,7})\s+'                    # 3 Customer Code
    r'(.*?)\s+'                        # 4 Customer Name (non-greedy, incl town)
    r'(\d{1,3})\s+'                    # 5 Rep Code (numeric, e.g. "07")
    r'(\d{4,})\s+'                     # 6 Product Code (anchors the split)
    r'(.*?)\s+'                        # 7 Product Name (non-greedy)
    r'(\S+)\s+'                        # 8 Packing
    r'(\d+)\s+'                        # 9 Qty
    r'(\d+)\s+'                        # 10 Free
    r'([\d,]+\.\d+)\s*$'               # 11 Amount
)


def parse_areawise_sales_statement_packing(text):
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
        m = _ROW.match(s) or _ROW_NUMREP.match(s)
        if m:
            (billno, date, _code, cust, _rep, _pcode,
             prod, _pack, qty, free, amt) = m.groups()
            rows.append([
                _clean_party(cust), area, prod.strip(), billno, date,
                qty, free, amt.replace(',', ''),
            ])
    return H, rows


def _clean_party(cust):
    """The customer field prints "<business name>, <town>[, <sub-town>]"; the
    area/town is already captured by the "Location :" band, so peel everything
    from the FIRST comma onward to leave a clean party name."""
    name = cust.strip()
    if ',' in name:
        name = name.split(',', 1)[0].strip()
    return name
