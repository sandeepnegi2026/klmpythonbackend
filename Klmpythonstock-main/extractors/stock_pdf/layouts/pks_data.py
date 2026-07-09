import re


def _pks_num(v):
    """Convert a PKS Data numeric token to float. Treats '--' and '-' as 0."""
    v = v.strip().replace(",", "")
    if v in ("", "-", "--", "---", "----", "-----"):
        return 0.0
    v = v.rstrip(".")
    try:
        return float(v)
    except ValueError:
        return None


def parse_pks_data(text):
    """PKS Data ERP: Product Name | unit | OpStk | Pur Qty | Total Rect | Sale Qty | Closing Qty"""
    records = []
    for line in text.splitlines():
        s = line.strip()
        if not s or len(s) < 5:
            continue
        if re.match(
            r"^(GSTIN|Stock Statement|Item Type|\(|Opening|Product Name|"
            r"Total |End Of|Software|page:|---+|===+|\d+/\d+$)",
            s, re.I,
        ):
            continue

        # Split tokens from the right: expect 5 numeric columns
        tokens = s.split()
        if len(tokens) < 3:
            continue

        # Pop numeric/dash tokens from the right
        nums_raw = []
        while tokens and (_pks_num(tokens[-1]) is not None):
            nums_raw.insert(0, tokens.pop())
        
        if len(nums_raw) < 5 or not tokens:
            continue

        # The remaining tokens are product name + optional unit
        # Check if last remaining token looks like a unit (e.g. 1*15GM, 1*30GM)
        pack = ""
        if tokens and re.match(r"^\d+\*\d+", tokens[-1]):
            pack = tokens.pop()

        name = " ".join(tokens)
        if not name or len(name) < 2:
            continue

        vals = [_pks_num(v) or 0.0 for v in nums_raw]

        # Columns: Opening Stock(0), Purchase Qty(1), Total Rect(2), Sale Qty(3), Closing Qty(4)
        r = {
            "product_name": name,
            "pack": pack,
            "opening_stock": vals[0],
            "purchase_stock": vals[1],
            "sales_qty": vals[3],
            "closing_stock": vals[4],
        }
        records.append(r)

    return records
