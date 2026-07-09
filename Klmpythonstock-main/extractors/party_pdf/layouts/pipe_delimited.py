import re

def _num(s):
    s = (s or "").strip().replace(",", "")
    if not s:
        return None
    try:
        return float(s)
    except Exception:
        return None

def parse_pipe_delimited(text):
    """Parse pipe-delimited pharma exports.
    Handles two distinct pipe layouts that both split cleanly on '|':
      (A) Item-wise sale register: 'SrNo|Entry No|Date|Account Name|Station|Mobile|Qty|Free|FreeAmt|BatchNo|Rate|...|Rate-A(Amt'
          - product name is a heading line above each item block; party varies per row (Account Name).
      (B) Tax invoice: 'PRODUCT|HSN|PKG.|QTY|FREE|RATE|GST|DIS%|AMOUNT|M.R.P|...'
          - single bill-to party in the invoice header (middle column on the line after a 'TO,' line).
    Returns (headers, rows) with headers mapped to canonical party field names.
    """
    lines = text.splitlines()

    # locate the column-header row: many '|' fields + known column tokens
    header_idx = None
    header_cells = None
    for i, ln in enumerate(lines):
        if ln.count("|") >= 4:
            cells = [c.strip() for c in ln.split("|")]
            joined = " ".join(c.lower() for c in cells)
            if ("account name" in joined or "product" in joined) and \
               ("qty" in joined) and ("rate" in joined or "amount" in joined):
                header_idx = i
                header_cells = cells
                break
    if header_idx is None:
        return [], []

    cols = [c.lower() for c in header_cells]
    n = len(cols)

    def find(*subs):
        for j, c in enumerate(cols):
            for s in subs:
                if s in c:
                    return j
        return None

    j_party = find("account name")
    j_area  = find("station", "area")
    j_date  = find("date")
    j_inv   = find("entry no", "bill no", "inv", "entry")
    j_qty   = find("qty")
    j_batch = find("batchno", "batch")
    j_rate  = find("rate")
    j_prod  = find("product", "description")
    j_pack  = find("pkg", "pack")

    # FREE column: exact 'free' (not 'freeamt')
    j_free = None
    for j, c in enumerate(cols):
        if c.strip() == "free":
            j_free = j
            break

    # AMOUNT: prefer an explicit AMOUNT header; else the last 'amt'/'rate-a' numeric column
    j_amt = find("amount")
    if j_amt is None:
        for j in range(n - 1, -1, -1):
            if "amt" in cols[j] or "amount" in cols[j] or cols[j].startswith("rate-a"):
                j_amt = j
                break
    if j_amt is None:
        j_amt = n - 1

    headers = ["Party Name", "Area", "Product Name", "Pack", "Batch",
               "Inv No", "Date", "Qty", "Free", "Rate", "Amount"]

    # invoice-style single bill-to party (layout B): party is the middle column
    # on the line immediately after a 'TO,' marker line, above the header.
    invoice_party = None
    for k in range(0, header_idx):
        ln = lines[k]
        if "|" in ln and re.search(r"\bto,?\b", ln.lower()):
            for m in range(k + 1, min(k + 3, header_idx)):
                parts = [p.strip() for p in lines[m].split("|")]
                if len(parts) >= 2 and parts[1] and re.search(r"[A-Za-z]{3}", parts[1]) \
                   and not re.search(r"gstin|date|book|time|phone|dl no", parts[1].lower()):
                    invoice_party = parts[1]
                    break
            if invoice_party:
                break

    rows = []
    current_product = None
    sep_chars = set("-=� +")

    for ln in lines[header_idx + 1:]:
        if "|" not in ln:
            # potential product heading line (layout A)
            t = ln.strip()
            if t and not (set(t) <= sep_chars) and len(t) > 2 \
               and re.match(r"^[A-Za-z]", t) and "�" not in t:
                current_product = t
            continue

        cells = [c.strip() for c in ln.split("|")]
        joined = " ".join(c.lower() for c in cells)

        # skip total / subtotal / separator rows
        if any(k in joined for k in ("item total", "sub total", "net total",
                                     "grand total", "party total", "total items")):
            continue
        if set(ln.replace("|", "")) <= sep_chars:
            continue

        def g(j):
            return cells[j] if (j is not None and j < len(cells)) else ""

        qty = _num(g(j_qty))
        amt = _num(g(j_amt))
        if qty is None and amt is None:
            continue

        prod = g(j_prod) if j_prod is not None else (current_product or "")
        if not prod:
            prod = current_product or ""
        party = g(j_party) if (j_party is not None and g(j_party)) else (invoice_party or "")

        rows.append([
            party,
            g(j_area),
            prod,
            g(j_pack),
            g(j_batch),
            g(j_inv),
            g(j_date),
            g(j_qty),
            g(j_free),
            g(j_rate),
            g(j_amt),
        ])

    return headers, rows