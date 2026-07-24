import re

def parse_customerwise_productwise(text):
    headers = ["Party Name", "Area", "Product Name", "Pack", "Inv No",
               "Date", "Batch", "Qty", "Free", "Rate", "Amount"]
    rows = []
    lines = text.splitlines()
    party = ""
    area = ""
    # line1: <product...> <inv> <DD/MM/YY> <rest...>
    # rest = <batch(>=1 token)> <qty> [free] <rate(float)>
    line1_re = re.compile(
        r'^(?P<head>.+?)\s+(?P<inv>\S+)\s+(?P<date>\d{2}/\d{2}/\d{2})\s+(?P<rest>.+)$')
    # wrap (line2): amount mrp [schmqty schmamt] pur.rate ptr  (amount = first number)
    wrap_re = re.compile(r'^-?\d+(?:\s+-?\d+(?:\.\d+)?){1,5}$')
    int_re = re.compile(r'^-?\d+$')
    float_re = re.compile(r'^-?\d+\.\d{1,2}$')
    skip_pref = ('Party Total', 'TOTAL', '-----', 'Product Name', 'Amount MRP',
                 'LIFECARE', 'Customerwise', 'For Company')
    pending = None  # a parsed product line awaiting its numeric wrap line
    for raw in lines:
        s = raw.strip()
        if not s:
            continue
        m = re.match(r'^Customer\s*:\s*\S+\s+(.*)$', s)
        if m:
            full = m.group(1).strip()
            area = ""
            if ',' in full:
                party, area = full.rsplit(',', 1)
                party = party.strip()
                area = area.strip()
            else:
                party = full
            pending = None
            continue
        if s.startswith(skip_pref):
            pending = None
            continue
        m1 = line1_re.match(s)
        if m1 and party:
            rest = m1.group('rest').split()
            if len(rest) >= 2 and float_re.match(rest[-1]):
                rate = rest[-1]
                trailing = rest[1:]
                batch = qty = free = None
                if len(trailing) == 2 and int_re.match(trailing[0]):
                    # batch qty rate
                    batch = rest[0]
                    qty = trailing[0]
                    free = ""
                elif (len(trailing) == 3 and int_re.match(trailing[0])
                      and int_re.match(trailing[1])):
                    # batch qty free rate
                    batch = rest[0]
                    qty = trailing[0]
                    free = trailing[1]
                elif (len(trailing) > 3 and int_re.match(rest[-2])
                      and int_re.match(rest[-3])):
                    # space-containing batch (e.g. "DP 436"): last 3 = qty free rate
                    batch = " ".join(rest[:-3])
                    qty = rest[-3]
                    free = rest[-2]
                if batch:
                    head = m1.group('head').strip()
                    toks = head.split()
                    # drop trailing sale-type flag ("A" sale / "S" sales-return)
                    if toks and toks[-1] in ('A', 'S'):
                        toks = toks[:-1]
                    product = " ".join(toks)
                    pending = [party, area, product, "", m1.group('inv'),
                               m1.group('date'), batch, qty, free, rate]
                    continue
            pending = None
            continue
        if pending is not None and wrap_re.match(s):
            amount = s.split()[0]  # first number of wrap line = Amount
            rows.append(pending + [amount])
            pending = None
            continue
        pending = None
    return headers, rows