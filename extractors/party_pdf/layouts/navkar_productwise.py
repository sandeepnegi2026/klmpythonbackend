import re


def parse_navkar_productwise(text):
    """'Product wise sale list' (NAVKAR APOTEK style). Customer names sit on a
    bare heading line; each sale row is
    '<date> <bill-no> <product> <HSN> <pack> <batch> <exp-date> <qty>'.
    A division/company line ('KLM LABORATORIES PED') and 'Customer Total'
    delimiters separate blocks. The report is quantity-only (no rate/amount),
    so only Qty is captured. A trailing ledger section (lines that are not
    date-prefixed rows) is naturally ignored by the row regex.
    """
    H = ["Party Name", "Product Name", "Pack", "Batch", "Inv No", "Date", "Qty"]
    rows, party = [], ""
    ROW = re.compile(
        r"^(\d{2}-\d{2}-\d{4})\s+([A-Z]{2,6}\s*\d+)\s+(.+?)\s+(\d{6,8})\s+"
        r"(\S+)\s+(\S+)\s+(\d{2}-\d{2}-\d{4})\s+(-?\d+)$"
    )
    SKIP = (
        "product wise sale list",
        "date bill no product",
        "customer total",
        "page no",
        "grand total",
        "company total",
        "opening",
        "closing",
    )
    for raw in text.split("\n"):
        s = re.sub(r"\s+", " ", raw.strip())
        if not s:
            continue
        sl = s.lower()

        m = ROW.match(s)
        if m and party:
            rows.append([
                party,
                m.group(3).strip(),   # product
                m.group(5),           # pack
                m.group(6),           # batch
                m.group(2).strip(),   # bill no -> Inv No
                m.group(1),           # date
                m.group(8),           # qty
            ])
            continue

        if any(k in sl for k in SKIP):
            continue
        # division / company header (e.g. 'KLM LABORATORIES PED') — not a party
        if "laboratories" in sl:
            continue
        # trailing ledger lines carry bill codes like 'KLM/2015/2526' — skip
        if re.search(r"\b[A-Z]+/\d+/\d+\b", s):
            continue
        # a bare uppercase customer heading becomes the current party
        if re.search(r"[A-Za-z]", s) and not re.search(r"\d{2}-\d{2}-\d{4}", s):
            party = s

    return H, rows
