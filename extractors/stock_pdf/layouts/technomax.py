import re

def _num(v):
    v = v.strip().replace(",", "")
    if v in ("", "-", "--", "---", "----"):
        return 0.0
    try:
        return float(v)
    except ValueError:
        return 0.0

def is_val(v):
    v = v.replace(",", "")
    if v in ("-", "--", "---", "----"): return True
    try:
        float(v)
        return True
    except:
        return False

def parse_technomax_stock(text):
    """
    Technomax Stock Statement
    Format:
    Sr. Product Details Packing Opening Receipt Sales Closing - Prev* Max*
    """
    records = []
    
    data_lines = []
    blocks = []
    current_block = []

    for line in text.splitlines():
        s = line.strip()
        if not s: continue
        
        low = s.lower()
        if "total values" in low or "without stock" in low or "purchase bills" in low or "company/doctor" in low:
            break
            
        if re.match(r"^(Company:|Division:|Date/Time:|Head Office:|Contact No:|EMail:|STOCK & SALES|page|GST No|Monthly Sales)", s, re.I):
            continue
            
        if s.lower().startswith("sr. product"):
            current_block = []
            continue
            
        # specifically ignore company name like "Manish Medical"
        if len(s) > 10 and ("medical" in low or "pharma" in low or "agencies" in low or "distributor" in low) and "asarawa" in low:
            continue
            
        tokens = s.split()
        if tokens[0].isdigit() and len(tokens) >= 5:
            temp = list(tokens)
            vals = []
            while temp and is_val(temp[-1]):
                vals.insert(0, temp.pop())
                
            if len(vals) >= 4:
                pack = temp.pop() if temp else ""
                sr = temp.pop(0) if temp else ""
                inline = " ".join(temp)
                
                blocks.append(current_block)
                current_block = []
                
                data_lines.append({
                    "sr": sr,
                    "inline": inline,
                    "pack": pack,
                    "vals": vals
                })
                continue
                
        current_block.append(s)
    blocks.append(current_block)

    for i, dl in enumerate(data_lines):
        prefix = []
        suffix = []
        
        before = blocks[i]
        if i == 0:
            prefix = before
        else:
            if len(before) == 1:
                if not dl["inline"]:
                    prefix = before
            elif len(before) >= 2:
                prefix = before[1:]
                
        after = blocks[i+1]
        if i == len(data_lines) - 1:
            suffix = after
        else:
            next_dl = data_lines[i+1]
            if len(after) == 1:
                if next_dl["inline"]:
                    suffix = after
            elif len(after) >= 2:
                suffix = [after[0]]
                
        name_parts = prefix + ([dl["inline"]] if dl["inline"] else []) + suffix
        name = " ".join(name_parts)
        
        # vals map:
        # Opening, Receipt, Sales, Closing
        opening = _num(dl["vals"][0])
        receipt = _num(dl["vals"][1])
        sales = _num(dl["vals"][2])
        closing = _num(dl["vals"][3])
        
        records.append({
            "product_name": name,
            "pack": dl["pack"],
            "opening_stock": opening,
            "purchase_stock": receipt,
            "sales_qty": sales,
            "closing_stock": closing,
        })
        
    return records
