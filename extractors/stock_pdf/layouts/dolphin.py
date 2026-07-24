import re

def _num(v):
    v = v.replace(",", "").strip()
    if not v or v in ("-", "--", "---"):
        return 0.0
    try:
        return float(v)
    except ValueError:
        return 0.0

def parse_dolphin_stock(text):
    """
    Dolphin ERP Stock Statement
    Columns: Product Name Packing Opening Receipt Issues Closing Sh.Exp Liquidation Sales Amount Closing Amount
    Zeros are omitted in stock and amounts.
    'Liquidation' contains 'Days' (or similar like 'Months'). We pivot around 'Days'.
    """
    records = []
    
    for line in text.splitlines():
        line = line.strip()
        # Pivot on 'Days' as it marks the end of the stock part
        if "Days" not in line:
            continue
            
        parts = line.split("Days")
        left = parts[0].strip()
        right = parts[1].strip() if len(parts) > 1 else ""
        
        left_tokens = left.split()
        if not left_tokens: continue
        
        # Pop the number right before 'Days' (Liquidation quantity)
        liq_days = left_tokens.pop()
        
        # Gather stock values from right to left
        stock_vals = []
        while left_tokens and left_tokens[-1].replace('.', '', 1).replace(',', '').isdigit():
            stock_vals.insert(0, _num(left_tokens.pop()))
            
        if not left_tokens:
            continue
            
        prod_name = " ".join(left_tokens)
        
        # Gather amounts from the right part
        right_tokens = right.split()
        amounts = [_num(t) for t in right_tokens]
        
        sales_amt = amounts[0] if len(amounts) == 2 else 0.0
        closing_amt = amounts[-1] if amounts else 0.0
        
        # Infer missing 0s from O, R, I, C
        o = r = i = c = 0.0
        if len(stock_vals) == 4:
            o, r, i, c = stock_vals
        elif len(stock_vals) == 3:
            # Usually O + R - I = C
            # If Sales (I) is 0: O + R = C
            if abs(stock_vals[0] + stock_vals[1] - stock_vals[2]) < 0.01:
                o, r, c = stock_vals
            # If Receipt (R) is 0: O - I = C
            elif abs(stock_vals[0] - stock_vals[1] - stock_vals[2]) < 0.01:
                o, i, c = stock_vals
            else:
                o, r, c = stock_vals # Fallback
        elif len(stock_vals) == 2:
            # e.g., 4 4 -> Opening 4, Closing 4
            o, c = stock_vals
        elif len(stock_vals) == 1:
            c = stock_vals[0]
            
        records.append({
            "product_name": prod_name,
            "opening_stock": o,
            "purchase_stock": r,
            "sales_qty": i,
            "closing_stock": c,
            "closing_stock_value": closing_amt
        })
        
    return records
