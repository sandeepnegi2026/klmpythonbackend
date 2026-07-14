"""Marg ERP 'SALE SUMMARY' party-level roll-up (party_pdf, text mode).

Vendor: UNIVERSAL MEDICAL AGENCY (KLM distributor).
Format: Marg ERP export titled 'SALE SUMMARY <from> - <to>' with a single
column header 'Party <Month> Total Value'. After a 'NET SALES' band there is
one row per party shaped:

    <PARTY NAME>  <May>  <Total Value>

  e.g.  AGRAWAL MEDICAL AGENCY 735 735.08

The middle 'May' column is a redundant truncated (int) copy of the Total Value
month figure -- on every row May == int(Total Value) -- so it is NOT a qty and
is ignored. The trailing two-decimal 'Total Value' column is the party's net
sale amount and is the only real number.

Column map:
  Party        -> party_name
  Total Value  -> amount / net_amount   (two-decimal, last column)
  (May column)  ignored (truncated int copy of Total Value)

No product/qty exists in the source, so a benign CORE_FIELD_EMPTY AMBER is
expected at worst.

Reconcile: sum(amount) == printed 'Value in Rs.' / '(Net Amount)' grand total
(e.g. 65584.64).

Skipped furniture: masthead / address / GSTIN / 'SALE SUMMARY' title /
dash rules / 'Party ... Total Value' header / 'NET SALES' band / 'Continued..' /
'Page No..' / 'Value in Rs.' / '(Net Amount)' / 'Report For :' / 'Company :'.
"""

import re

# Total Value column: two-decimal money (no thousands separators observed but
# tolerate them just in case).
_NUM2 = r'-?\d[\d,]*\.\d{2}'
# May column: bare integer (truncated value).
_INT = r'-?\d[\d,]*'

# <name> <int> <dd.dd>$
_ROW_RE = re.compile(
    r'^(?P<name>.*?[A-Za-z].*?)\s+(?P<may>' + _INT + r')\s+'
    r'(?P<amt>' + _NUM2 + r')\s*$'
)

_SKIP_PREFIXES = (
    'SALE SUMMARY',
    'PARTY MAY',
    'PARTY JAN', 'PARTY FEB', 'PARTY MAR', 'PARTY APR',
    'PARTY JUN', 'PARTY JUL', 'PARTY AUG', 'PARTY SEP',
    'PARTY OCT', 'PARTY NOV', 'PARTY DEC',
    'NET SALES',
    'CONTINUED',
    'PAGE NO',
    'VALUE IN RS',
    '(NET AMOUNT)',
    'REPORT FOR',
    'COMPANY :',
    'GSTIN',
    'PHONE',
)


def parse_marg_sale_summary_party(text):
    headers = ["Party Name", "Amount"]
    rows = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        up = line.upper()
        # dash rules
        if set(line) <= set('-'):
            continue
        if any(up.startswith(p) for p in _SKIP_PREFIXES):
            continue
        m = _ROW_RE.match(line)
        if not m:
            continue
        name = m.group('name').strip()
        if not name:
            continue
        amt = m.group('amt').replace(',', '')
        rows.append([name, amt])
    return headers, rows
