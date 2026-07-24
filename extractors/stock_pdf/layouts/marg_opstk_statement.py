import io
import pdfplumber
import re

from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_numbers,
    _split_product_pack,
)


def _decode_pharmabyte(word):
    """Decode Pharmabyte/Sky Way interleaved item codes.
    
    These ERPs embed numeric item-code digits between the letters of
    the product name, e.g.  IM05E7L2B8OOST → MELBOOST,
    1N7I6O9CLEAN → NIOCLEAN.  Strip the digits, then remove the
    leading 'I' item-code prefix when present.
    """
    if not re.search(r"[A-Za-z]", word) or not re.search(r"\d", word):
        return word
    alpha = re.sub(r"[^A-Za-z-]", "", word)
    if alpha and alpha[0] == "I":
        alpha = alpha[1:]
    return alpha


def _looks_pharmabyte(text):
    """Return True if the text has Pharmabyte-style interleaved codes."""
    # Check first few product lines for the telltale digit-letter mixing pattern
    # e.g. 'IM05E7L2B8OOST' or '1N7I6O9CLEAN'
    return bool(re.search(r"(?:^|[\n])(?:I[A-Z]\d{2}|1[A-Z]\d[A-Z])", text))


# A marg stock data-cell prints as an integer immediately followed by '.' and then
# a space/end-of-line or another digit (e.g. '5. 4. 234.32' / '10. 10.').  A genuine
# KLM division band ('KLM COSMOCOR', 'KLM LAB (DERMACOR)', 'KLM LAB.
# PVT.LTD.(PEDIATRIC DIV.)-200') never contains one — its punctuation is letter-dots
# ('PVT.LTD.') and hyphen-codes ('-001057', '-200'), never a digit-dot cell.
_MARG_DATA_CELL = re.compile(r"\d+\.(?:\s|$)|\d+\.\d")


def _is_klm_division_band(s):
    """A line is a KLM division band only if it starts 'KLM ' AND carries no marg
    stock data cell. This stops product rows whose interleaved item code descrambles
    to a leading 'KLM ' token (e.g. 'I2K2L5M8 3D3 NANO SHOTS 5. 4. 234.32 1. 52.72'
    -> 'KLM D3 NANO SHOTS 5. 4. ...', 'I0K1L7M2 3KLIN AHA FACE WASH ...') from being
    swallowed as a band and silently dropped (E1) while also corrupting the division
    label of every following row."""
    if not re.match(r"^KLM\s", s, re.I):
        return False
    return not _MARG_DATA_CELL.search(s)


def _extract_clean_words_from_pdf(file_bytes):
    all_words = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            chars = page.chars
            lines_dict = {}
            for c in chars:
                matched_y = None
                for y in lines_dict:
                    if abs(y - c["top"]) < 2.0:
                        matched_y = y
                        break
                if matched_y is None:
                    matched_y = c["top"]
                lines_dict.setdefault(matched_y, []).append(c)
                
            for y, lc in sorted(lines_dict.items()):
                runs = []
                current_run = []
                last_x = -1
                for c in lc:
                    if c['x0'] < last_x - 3.0:
                        if current_run:
                            runs.append(current_run)
                        current_run = [c]
                    else:
                        current_run.append(c)
                    last_x = c['x0'] + c['width']
                if current_run:
                    runs.append(current_run)
                
                run_info = []
                for r in runs:
                    x0 = r[0]['x0']
                    x1 = r[-1]['x0'] + r[-1]['width']
                    run_info.append({'x0': x0, 'x1': x1, 'chars': r})
                
                kept_runs = []
                for i, r in enumerate(run_info):
                    is_overwritten = False
                    for j in range(i + 1, len(run_info)):
                        later_r = run_info[j]
                        overlap_start = max(r['x0'], later_r['x0'])
                        overlap_end = min(r['x1'], later_r['x1'])
                        if overlap_end > overlap_start:
                            overlap_width = overlap_end - overlap_start
                            r_width = r['x1'] - r['x0']
                            if r_width > 0 and (overlap_width / r_width) > 0.5:
                                is_overwritten = True
                                break
                    if not is_overwritten:
                        kept_runs.append(r)
                
                kept_runs.sort(key=lambda r: r['x0'])
                for r in kept_runs:
                    r['chars'].sort(key=lambda c: c['x0'])
                    run_str = ""
                    word_x0 = None
                    last_x = None
                    for c in r['chars']:
                        if c['text'].isspace():
                            if run_str.strip():
                                all_words.append({'text': run_str.strip(), 'x0': word_x0, 'x1': last_x, 'top': y, 'page': page.page_number})
                            run_str = ""
                            word_x0 = None
                            last_x = c['x0'] + c['width']
                            continue
                            
                        if last_x is not None and c['x0'] - last_x > 4.0:
                            if run_str.strip():
                                all_words.append({'text': run_str.strip(), 'x0': word_x0, 'x1': last_x, 'top': y, 'page': page.page_number})
                            run_str = ""
                            word_x0 = None
                            
                        run_str += c['text']
                        if word_x0 is None:
                            word_x0 = c['x0']
                        last_x = c['x0'] + c['width']
                    if run_str.strip():
                        all_words.append({'text': run_str.strip(), 'x0': word_x0, 'x1': last_x, 'top': y, 'page': page.page_number})
                        
    return all_words


def _parse_marg_opstk_with_coords(file_bytes):
    records = []
    division = ""
    words = _extract_clean_words_from_pdf(file_bytes)
    if not words:
        return []
        
    pages_words = {}
    for w in words:
        pages_words.setdefault(w['page'], []).append(w)
        
    headers = {}
    for page_num in sorted(pages_words.keys()):
        page_words = pages_words[page_num]
        
        page_headers = {}
        for w in page_words:
            text_up = w['text'].upper()
            if text_up in ['OPSTK', 'P.QTY', 'P.VAL', 'P.SCH', 'S.QTY', 'S.SCH', 'S.VAL', 'STKAD', 'CLSTK', 'CLVAL', 'ORDER']:
                page_headers[text_up] = w['x1']
        
        if page_headers:
            headers = page_headers
            
        if not headers:
            continue
            
        lines_dict = {}
        for w in page_words:
            matched_y = None
            for y in lines_dict:
                if abs(y - w['top']) < 4.0:
                    matched_y = y
                    break
            if matched_y is None:
                matched_y = w['top']
            lines_dict.setdefault(matched_y, []).append(w)
            
        is_pharmabyte = _looks_pharmabyte(" ".join(w['text'] for w in page_words[:200]))
            
        for y, line_words in sorted(lines_dict.items()):
            line_words.sort(key=lambda w: w['x0'])
            line_text = " ".join(w['text'] for w in line_words)
            
            s = line_text.strip()
            if _skip_line(s) or "DIVI" in s.upper():
                continue
            if _is_klm_division_band(s):
                division = s
                continue
            if re.match(r"^(VISNAGAR|Stock and Sale|Item\s+OpStk)", s):
                continue
            if "SOCKANDSAE" in s.replace(" ", "").upper():
                continue
                
            min_header_x = min(headers.values()) if headers else 100.0
            
            name_words = []
            val_words = []
            
            split_words = []
            for w in line_words:
                m = re.match(r"^([A-Za-z0-9\-]+(?:GM|ML|MG))(\d+\.?\d*)$", w['text'], re.I)
                if m:
                    name_part = m.group(1)
                    num_part = m.group(2)
                    split_words.append({'text': name_part, 'x0': w['x0'], 'x1': w['x0'] + 10, 'top': w['top']})
                    split_words.append({'text': num_part, 'x0': w['x1'] - 10, 'x1': w['x1'], 'top': w['top']})
                else:
                    split_words.append(w)
            
            for w in split_words:
                text_clean = w['text'].replace(',', '')
                is_num = False
                try:
                    float(text_clean)
                    is_num = True
                except ValueError:
                    pass
                    
                if is_num and w['x1'] > min_header_x - 15:
                    val_words.append(w)
                else:
                    name_words.append(w)
                    
            name = " ".join(w['text'] for w in name_words)
            name = re.sub(r"V[SI]\d{4}", " ", name)
            name = re.sub(r"MF\d{3}", " ", name)
            name = re.sub(r"\s+", " ", name).strip()
            
            name, pack = _split_product_pack(name)
            name = re.sub(r"^[A-Z]{1,2}\d{3,5}\s*", "", name).strip()
            
            if is_pharmabyte:
                p_words = name.split()
                if p_words:
                    first_decoded = _decode_pharmabyte(p_words[0])
                    if first_decoded != p_words[0]:
                        p_words[0] = first_decoded
                    name = " ".join(p_words)
            
            if not name or len(name) < 3 or "*" in name:
                continue
            if "DIVISION" in name.upper() or "DIVISON" in name.upper():
                continue
                
            row_vals = {}
            for w in val_words:
                x1 = w['x1']
                text = w['text'].replace(',', '')
                val = float(text)
                
                closest_header = None
                min_dist = 9999
                for h, h_x1 in headers.items():
                    dist = abs(x1 - h_x1)
                    if dist < min_dist:
                        min_dist = dist
                        closest_header = h
                        
                if closest_header:
                    row_vals[closest_header] = val
                    
            if not row_vals:
                continue
                
            r = {"product_name": name, "pack": pack, "division": division}
            if 'OPSTK' in row_vals: r['opening_stock'] = row_vals['OPSTK']
            if 'P.QTY' in row_vals: r['purchase_stock'] = row_vals['P.QTY']
            if 'P.VAL' in row_vals: r['purchase_value'] = row_vals['P.VAL']
            if 'S.QTY' in row_vals: r['sales_qty'] = row_vals['S.QTY']
            if 'S.VAL' in row_vals: r['sales_value'] = row_vals['S.VAL']
            if 'CLSTK' in row_vals: r['closing_stock'] = row_vals['CLSTK']
            if 'CLVAL' in row_vals: r['closing_stock_value'] = row_vals['CLVAL']
            # P.Sch / S.Sch (purchase/sales scheme = free goods) are bucketed into
            # row_vals above (their header words are in the anchor list) but were
            # historically never emitted, which broke the stock identity
            # (op + pur + pfree - sales - sfree = closing) on every row with
            # free-goods movement (VISNAGAR MF070: 63% false SANITY_FAILED).
            # Emit them ONLY when the row also carries a core stock column:
            # letterhead address lines ("105,106,...ANAND MARKET,... Ph:02765...")
            # bucket their phone-number fragments into the scheme slots and must
            # remain all-zero phantom rows exactly as before this fix.
            if any(k in row_vals for k in ('OPSTK', 'P.QTY', 'P.VAL', 'S.QTY',
                                           'S.VAL', 'CLSTK', 'CLVAL')):
                if 'P.SCH' in row_vals: r['purchase_free'] = row_vals['P.SCH']
                if 'S.SCH' in row_vals: r['sales_free'] = row_vals['S.SCH']

            records.append(r)
    return records


def _extract_clean_text_from_pdf(file_bytes):
    import io
    import pdfplumber
    page_texts = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            clean_lines = []
            chars = page.chars
            lines_dict = {}
            for c in chars:
                matched_y = None
                for y in lines_dict:
                    if abs(y - c["top"]) < 2.0:
                        matched_y = y
                        break
                if matched_y is None:
                    matched_y = c["top"]
                lines_dict.setdefault(matched_y, []).append(c)
                
            clean_chars = []
            for y, lc in sorted(lines_dict.items()):
                runs = []
                current_run = []
                last_x = -1
                for c in lc:
                    if c['x0'] < last_x - 3.0:
                        if current_run:
                            runs.append(current_run)
                        current_run = [c]
                    else:
                        current_run.append(c)
                    last_x = c['x0'] + c['width']
                if current_run:
                    runs.append(current_run)
                
                run_info = []
                for r in runs:
                    x0 = r[0]['x0']
                    x1 = r[-1]['x0'] + r[-1]['width']
                    run_info.append({'x0': x0, 'x1': x1, 'chars': r})
                
                kept_runs = []
                for i, r in enumerate(run_info):
                    is_overwritten = False
                    for j in range(i + 1, len(run_info)):
                        later_r = run_info[j]
                        overlap_start = max(r['x0'], later_r['x0'])
                        overlap_end = min(r['x1'], later_r['x1'])
                        if overlap_end > overlap_start:
                            overlap_width = overlap_end - overlap_start
                            r_width = r['x1'] - r['x0']
                            if r_width > 0 and (overlap_width / r_width) > 0.5:
                                is_overwritten = True
                                break
                    if not is_overwritten:
                        kept_runs.append(r)
                
                kept_runs.sort(key=lambda r: r['x0'])
                line_text = ""
                for r in kept_runs:
                    r['chars'].sort(key=lambda c: c['x0'])
                    run_str = ""
                    word_x0 = None
                    last_x = None
                    for c in r['chars']:
                        if c['text'].isspace():
                            if run_str.strip():
                                # dummy logic to keep sync with clean_words
                                pass
                            run_str = ""
                            word_x0 = None
                            last_x = c['x0'] + c['width']
                            continue
                            
                        if last_x is not None and c['x0'] - last_x > 4.0:
                            run_str += " "
                            
                        run_str += c['text']
                        if word_x0 is None:
                            word_x0 = c['x0']
                        last_x = c['x0'] + c['width']
                    
                    if line_text:
                        line_text += " "
                    line_text += run_str
                clean_lines.append(line_text)
            
            page_text = "\n".join(clean_lines)
            page_texts.append(page_text)
    return "\n".join(page_texts)


def parse_marg_opstk_statement(text, file_bytes=None):
    """Marg OpStk Statement: item codes merged into product names."""
    if file_bytes is not None:
        try:
            records = _parse_marg_opstk_with_coords(file_bytes)
            if records:
                return records
        except Exception:
            pass
            
        try:
            text = _extract_clean_text_from_pdf(file_bytes)
        except Exception:
            pass
            
    records = []
    division = ""
    is_pharmabyte = _looks_pharmabyte(text)
    for line in text.splitlines():
        s = line.strip()
        if _skip_line(s) or "DIVI" in s.upper():
            continue
        if _is_klm_division_band(s):
            division = s
            continue
        if re.match(r"^(VISNAGAR|Stock and Sale|Item\s+OpStk)", s):
            continue
        if "SOCKANDSAE" in s.replace(" ", "").upper():
            continue
        cleaned = re.sub(r"V[SI]\d{4}", " ", s)
        cleaned = re.sub(r"MF\d{3}", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        prod, tail, _ = _split_product_numbers(cleaned)
        if not prod or len(tail) < 2:
            continue
        name, pack = _split_product_pack(prod)
        name = re.sub(r"^[A-Z]{1,2}\d{3,5}\s*", "", name).strip()
        
        # Decode Pharmabyte interleaved item codes if detected
        if is_pharmabyte:
            words = name.split()
            if words:
                first_decoded = _decode_pharmabyte(words[0])
                if first_decoded != words[0]:
                    words[0] = first_decoded
                name = " ".join(words)
        
        if not name or len(name) < 3 or "*" in name:
            continue
        if "DIVISION" in name.upper() or "DIVISON" in name.upper():
            continue
        vals = _nums(tail)
        if len(vals) < 2:
            continue
        r = {"product_name": name, "pack": pack, "division": division}
        n = len(vals)
        
        has_order = False
        if n >= 3 and vals[-2] > vals[-1] and vals[-2] > vals[-3]:
            has_order = True
            
        if has_order:
            clval_idx = -2
        else:
            clval_idx = -1
            
        r["closing_stock_value"] = vals[clval_idx]
        r["closing_stock"] = vals[clval_idx - 1] if n >= 2 else vals[0]
        
        if n >= 4:
            if vals[1] > 500 and vals[1] > vals[0] * 5:
                # Likely P.Qty, P.Val where OpStk is missing
                pass
            else:
                r["opening_stock"] = vals[0]
        elif n == 3 and not has_order:
            r["opening_stock"] = vals[0]
            
        if n >= 8:
            r["purchase_stock"] = vals[1]
            r["purchase_value"] = vals[2]
            r["sales_value"] = vals[clval_idx - 2]
            r["sales_qty"] = vals[clval_idx - 4] if (clval_idx - 4) >= 3 else vals[3]
        elif n >= 5:
            # If n is between 5 and 7, we usually have OpStk, S.Qty, S.Val, ClStk, ClVal
            if n == 7 and vals[1] > 500 and vals[1] > vals[0] * 5:
                pass
            else:
                r["opening_stock"] = vals[0]
        records.append(r)
    return records
