from core.canonical import DIVISIONS


def extract_header_fields(text):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    result = {}
    for line in lines[:10]:
        low = line.lower()
        # Extract GSTIN if present
        if "gstin" in low:
            import re
            gm = re.search(r"\b(\d{2}[A-Z]{5}\d{4}[A-Z]\d[A-Z\d]{2})\b", line)
            if gm:
                result["vendor_gstin"] = gm.group(1)
            continue
        if line.isdigit() or len(line) < 3 or low.startswith("page"):
            continue
            
        import re
        # Strip out company, division, or time suffixes rather than skipping the whole line
        clean_line = re.sub(r'(?i)\s*(company|division|date/time|time)\s*:.*', '', line).strip()
        if len(clean_line) < 3 or not re.search(r'[a-zA-Z]', clean_line):
            continue
            
        low_clean = clean_line.lower()

        # Safely catch spaced-out anomalies without risking legitimate vendor names
        if "s t o c k" in low_clean or "r e p o r t" in low_clean:
            continue
            
        has_skip = False
        if re.search(r'stock(?!(well|ist))', low_clean):
            has_skip = True
        elif any(k in low_clean for k in ["from", "product", "item", "report", "monthly", "gstin"]):
            has_skip = True
            
        if not has_skip:
            result["vendor_name"] = re.sub(r'(?i)\s*TO\s*:.*', '', clean_line).strip()
            break
    result.setdefault("vendor_name", lines[0] if lines else "")
    # Report period comes from the upload-time month selection, not the document.
    for line in lines[:15]:
        upper = line.upper()
        for div in DIVISIONS:
            if div in upper:
                result["division"] = div.replace(" ", "")
                break
        if "division" in result:
            break
    title = next((l for l in lines[:10] if "stock" in l.lower()), "")
    if title:
        result["report_type_label"] = title
    return result
