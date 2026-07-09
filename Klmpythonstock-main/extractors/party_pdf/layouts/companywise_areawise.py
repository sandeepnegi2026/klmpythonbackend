import re

def parse_companywise_areawise(text):
    # Companywise AreawiseSalesDetail (Sri Nagendra Drug Agencies style).
    # "Party" in this report == AREA heading (no per-customer name exists).
    # Layout per group: AREA heading -> PRODUCT name line -> bill rows
    #   (BillNo Date [Batch] Rate Qty Value [Free Qty Value] [Repl Qty Value]) ->
    #   continuation rows (same bill, extra batch: [Batch] Rate Qty Value ...) ->
    #   PRODUCT subtotal line -> ... -> AREA subtotal line.
    # WARNING: in flattened text a Free/Replacement-only continuation row is
    # indistinguishable from a Billed continuation row; this parser counts both
    # as Billed, giving ~+0.15% over the printed Billed total. A faithful
    # implementation must use word x-positions to split Billed/Free/Replacement.
    headers = ["Area", "Product Name", "Inv No", "Date", "Batch",
               "Rate", "Qty", "Amount"]
    lines = [l.strip() for l in text.splitlines()]
    n = len(lines)

    def is_noise(l):
        return (not l) or l.startswith((
            "Sri Nagendra", "Companywise", "Date:",
            "Bill Bill", "No.Date", "Grand Total"))

    # full bill row: BillNo Date [Batch] Rate Qty Value (+ optional free/repl pairs)
    re_full = re.compile(
        r"^(\d{1,6})\s+(\d{2}/\d{2}/\d{2})\s+"
        r"(?:([A-Za-z0-9][\w/.-]*)\s+)?"
        r"(\d+\.\d{2})\s+(\d+)\s+(\d+\.\d{2})(?:\s+\d+\s+\d+\.\d{2})*$")
    # continuation row (same bill, extra batch): [Batch] Rate Qty Value (...)
    # batch must start with a letter so we never swallow a numeric subtotal.
    re_cont = re.compile(
        r"^(?:([A-Za-z][\w/.-]*)\s+)?"
        r"(\d+\.\d{2})\s+(\d+)\s+(\d+\.\d{2})(?:\s+\d+\s+\d+\.\d{2})*$")
    # subtotal line: <name ending in a non-digit> <count> <qty> <value> (...)
    re_sum = re.compile(
        r"^(.*?\D)\s+(\d+)\s+(\d+)\s+(\d+\.\d{2})(?:\s+\d+\s+\d+\.\d{2})*$")

    typ = [None] * n
    for i, l in enumerate(lines):
        if is_noise(l):
            typ[i] = "noise"
        elif re_full.match(l):
            typ[i] = "bill"
        elif re_cont.match(l):
            typ[i] = "cont"
        else:
            typ[i] = "text"

    def nxt(i):
        j = i + 1
        while j < n and typ[j] == "noise":
            j += 1
        return j

    rows = []
    cur_area = ""
    cur_prod = ""
    last_bn = ""
    last_dt = ""
    i = 0
    while i < n:
        t = typ[i]
        l = lines[i]
        if t == "noise":
            i += 1
            continue
        if t == "bill":
            m = re_full.match(l)
            last_bn, last_dt = m.group(1), m.group(2)
            rows.append([cur_area, cur_prod, m.group(1), m.group(2),
                         m.group(3) or "", m.group(4), m.group(5), m.group(6)])
            i += 1
            continue
        if t == "cont":
            m = re_cont.match(l)
            rows.append([cur_area, cur_prod, last_bn, last_dt,
                         m.group(1) or "", m.group(2), m.group(3), m.group(4)])
            i += 1
            continue
        # plain text line: either a subtotal (skip), a product header, or an area heading
        if re_sum.match(l):
            i += 1
            continue
        j = nxt(i)
        if j < n and typ[j] == "bill":
            cur_prod = l            # product name precedes its bill rows
        else:
            cur_area = l            # otherwise it is an area heading
            cur_prod = ""
        i += 1
    return headers, rows