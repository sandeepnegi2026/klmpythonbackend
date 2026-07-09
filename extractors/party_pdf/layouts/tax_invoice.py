import re


def parse_tax_invoice(text):
    """Single-buyer tax invoice (MARG ERP NANO style). One 'To Buyer Name : X'
    header names the party; each line item is
    '<HSN> <product ... pack mfr batch> <exp> <qty> <mrp> <rate> <disc%> <gst%> <amount>'.
    The buyer becomes the Party Name on every line. A glyph-garbled line (rare)
    simply fails the row regex and is skipped.
    """
    H = ["Party Name", "Product Name", "Qty", "Rate", "Amount"]
    rows, party = [], ""
    ROW = re.compile(
        r"^(\d{6,8})\s+(.+?)\s+(\d{1,2}/\d{2})\s+(\d+)\s+([\d.]+)\s+"
        r"([\d.]+)\s+([\d.]+)\s+(\d+)%\s+([\d.]+)$"
    )
    for raw in text.split("\n"):
        s = re.sub(r"\s+", " ", raw.strip())
        if not s:
            continue
        if not party:
            mb = re.search(r"To Buyer Name\s*:\s*(.+)$", s)
            if mb:
                party = mb.group(1).strip()
                continue
        m = ROW.match(s)
        if m and party:
            rows.append([
                party,
                m.group(2).strip(),   # product (+ pack/mfr/batch)
                m.group(4),           # qty
                m.group(6),           # rate
                m.group(9),           # amount
            ])
    return H, rows
