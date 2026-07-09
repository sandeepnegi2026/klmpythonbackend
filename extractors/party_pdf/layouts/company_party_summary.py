import re

def parse_company_party_summary(text):
    """Parse the 'COMPANY/PARTY WISE SALES SUMMARY' layout.
    Division headers look like 'N. KLM XXX'; party rows are
    '<PARTY NAME + AREA>  <SALES>  <RETURN>  <AMOUNT>' with two-decimal numbers.
    AMOUNT (net) is the canonical amount; SUB TOTAL / TOTAL / header / page
    furniture lines are skipped. Reconciles exactly to the printed TOTAL.
    """
    headers = ["Division", "Party Name", "Sales", "Return", "Amount"]
    rows = []
    division = ""
    num = r'-?\d[\d,]*\.\d{2}'
    line_re = re.compile(
        r'^(?P<name>.*?\S)\s+(?P<sales>' + num + r')\s+(?P<ret>' + num +
        r')\s+(?P<amt>' + num + r')\s*$')
    div_re = re.compile(r'^\s*\d+\.\s+(KLM.*\S)\s*$')
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        m = div_re.match(line)
        if m:
            division = m.group(1).strip()
            continue
        s = line.strip()
        up = s.upper()
        # skip totals, headers, separators, page furniture
        if (up.startswith('TOTAL') or up.startswith('SUB TOTAL') or
                up.startswith('SNO') or 'END OF REPORT' in up or
                up.startswith('COMPANY/PARTY') or set(s) <= set('-')):
            continue
        m = line_re.match(s)
        if not m:
            continue
        name = m.group('name').strip()
        # a real party row must contain letters (skips bare-number sub-total lines)
        if not re.search(r'[A-Za-z]', name):
            continue
        rows.append([division, name,
                     m.group('sales'), m.group('ret'), m.group('amt')])
    return headers, rows