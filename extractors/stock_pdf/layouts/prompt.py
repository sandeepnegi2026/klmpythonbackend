import re

from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_numbers,
    _split_product_pack,
)


def parse_prompt(text):
    """Prompt ERP Stock Statement text layout"""
    records = []
    for line in text.splitlines():
        s = line.strip()
        if _skip_line(s):
            continue
            
        # Lines start with an index number
        if not re.match(r"^\d+\s", s):
            continue
            
        # Strip index
        s = re.sub(r"^\d+\s+", "", s)
        
        # Strip trailing order format: "A3Mn Order(s): 3 0 / 0 / 0 = 0"
        s = re.sub(r"\s+\d+\s*/.*$", "", s)
        
        prod, tail, exp = _split_product_numbers(s)
        if not prod or len(tail) < 6:
            continue
            
        name, pack = _split_product_pack(prod)
        vals = _nums(tail)
        
        # vals: OpStk(0), Pur(1), Sales(2), Free(3), Inst(4), ClStk(5), Amount(6)
        if len(vals) < 6:
            continue
            
        r = {
            "product_name": name,
            "pack": pack,
            "opening_stock": vals[0],
            "purchase_stock": vals[1],
            "sales_qty": vals[2],
            "sales_free": vals[3],
            "closing_stock": vals[5],
        }
        
        if len(vals) >= 7:
            r["sales_value"] = vals[6]
            
        if exp:
            r["expiry"] = exp
            
        records.append(r)
        
    return records
