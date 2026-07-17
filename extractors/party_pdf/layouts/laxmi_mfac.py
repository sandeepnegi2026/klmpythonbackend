import re

def parse_laxmi_mfac(text):
    lines = text.splitlines()
    headers = ["Date", "Inv No", "Party Name", "Product Name", "Batch",
               "Qty", "Free", "Rate", "Amount"]
    # Detail row: DATE INVNO <party + dl-license + 6digit-pin + product + batch> QTY FREE SCH% CASH% RATE
    detail_re = re.compile(
        r'^(\d{2}-\d{2}-\d{4})\s+(\d{6,})\s+(.*?)\s+'
        r'(-?\d+)\s+(\d+)\s+(\d+\.\d{2})\s+(\d+\.\d{2})\s+(\d+\.\d{2})\s*$')
    # In a separate per-page block (after the "Net Selling Rate Net Value" header)
    # each line is "<rate> <net_value>" in the SAME ORDER as the detail rows.
    value_re = re.compile(r'^(-?\d+\.\d{2})\s+(-?\d+\.\d{2})$')

    def split_middle(mid):
        # mid = "PARTY NAME <DL License No> <6-digit Pin Code> PRODUCT NAME BATCH"
        # Pin code is a 6-digit number (or 000000). Product+Batch follow it; Party+License precede it.
        party = product = batch = ""
        pm = re.search(r'\b(?:\d{6}|000000)\b', mid)
        if pm:
            before = mid[:pm.start()].strip()
            after = mid[pm.end():].strip()
            t = after.rsplit(' ', 1)
            if len(t) == 2:
                product, batch = t[0].strip(), t[1].strip()
            else:
                product = after
            party = before  # party name + trailing DL license number
        else:
            party = mid
        return party, product, batch

    rows = []
    pending = []      # detail tuples on the current page, awaiting their Net Value lines
    vbuf = []         # net values collected after the "Net Value" header on this page
    in_values = False

    def flush():
        for i, d in enumerate(pending):
            date, invno, mid, qty, free, sch, cash, rate = d
            party, product, batch = split_middle(mid)
            if i < len(vbuf):
                amount = "%.2f" % vbuf[i]            # exact printed Net Value
            else:
                amount = "%.2f" % round(float(rate) * int(qty), 2)  # fallback
            rows.append([date, invno, party, product, batch,
                         qty, free, rate, amount])

    for ln in lines:
        s = ln.strip()
        if 'Net Selling Rate Net Value' in s:
            in_values = True
            vbuf = []
            continue
        dm = detail_re.match(s)
        if dm:
            if in_values:
                # a new page's detail block began -> emit the previous page
                flush()
                pending = []
                vbuf = []
                in_values = False
            pending.append(dm.groups())
            continue
        if in_values:
            vm = value_re.match(s)
            if vm:
                vbuf.append(float(vm.group(2)))
    if pending:
        flush()
    return headers, rows