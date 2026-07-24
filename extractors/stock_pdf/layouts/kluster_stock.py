import re

def _num(v):
    v = v.replace(",", "").strip()
    if v in ("-", "--", "---", ""):
        return 0.0
    try:
        return float(v)
    except ValueError:
        return 0.0

def is_val(v):
    v = v.replace(",", "")
    if v in ("-", "--", "---"): return True
    try:
        float(v)
        return True
    except:
        return False

def parse_kluster_stock(text):
    """
    Kluster Software Stock Statement
    Format:
    [Division] Code Product Packing LMS OP.Stock Rcpts Sales HOS.SALES CL.Stk CL.Value
    """
    records = []
    current_div = ""
    
    for line in text.splitlines():
        line = line.strip()
        if not line: continue
        
        low = line.lower()
        if "total values" in low or "grand total" in low:
            break
            
        if "page" in low or "stockstatement" in low or "name code" in low or "mercury agencies" in low:
            continue
            
        tokens = line.split()
        if len(tokens) < 10:
            continue
            
        # Check if last 7 are values
        if all(is_val(t) for t in tokens[-7:]):
            vals = [_num(t) for t in tokens[-7:]]
            pack = tokens[-8]
            rest = tokens[:-8]
            
            # Find code
            code_idx = -1
            for i, t in enumerate(rest):
                if t.isdigit() and len(t) >= 4:
                    code_idx = i
                    break
                    
            if code_idx > 0:
                current_div = " ".join(rest[:code_idx])
                code = rest[code_idx]
                prod = " ".join(rest[code_idx+1:])
            elif code_idx == 0:
                code = rest[0]
                prod = " ".join(rest[1:])
            else:
                code = ""
                prod = " ".join(rest)
                
            records.append({
                "division": current_div,
                "product_code": code,
                "product_name": prod,
                "pack": pack,
                "opening_stock": vals[1],
                "purchase_stock": vals[2],
                "sales_qty": vals[3],
                "closing_stock": vals[5],
                "closing_stock_value": vals[6]
            })
            
    return records
