import re

def parse_rp_pharma_itemwise(text):
    headers = ["Party Code","Party Name","Area","Product Name","Pack",
               "Batch","Inv No","Date","Rate","Qty","Free","Scheme","Amount"]
    rows = []
    lines = text.splitlines()
    # item/product header: "250 BLEMGUARD-TX FACE SERUM 1X30ML"
    item_re = re.compile(r'^\s*(\d{1,6})\s+(.+?)\s+(\d+X[\dA-Za-z./]+)\s*$')
    # detail: BillNo(8d) Date(dd/mm/yy) SM PartyCode PartyName... Batch Rate Qty [FreeMarker Scheme] [Value] Expiry(mm/yy)
    det_re = re.compile(
        r'^\s*(\d{8})\s+(\d{2}/\d{2}/\d{2})\s+(\d+)\s+(\d+)\s+(.+?)\s+(\S+)\s+'  # bill date sm pcode pname batch
        r'([\d.]+)\s+(\d+)'                                                      # rate qty
        r'(?:\s+([A-Za-z])\s+([\d.]+))?'                                         # opt free-marker + scheme amount
        r'(?:\s+([\d.]+))?'                                                      # opt value (absent when qty=0)
        r'\s+(\d{2}/\d{2})\s*$')                                                 # expiry
    skip = ("Item Total", "Final Total", "R.P.PHARMA", "Print Date", "Bill ", "No.")
    cur_product = ""
    cur_pack = ""
    for i, raw in enumerate(lines):
        line = raw.rstrip()
        m = det_re.match(line)
        if m:
            bill, date, sm, pcode, pname, batch, rate, qty, fmark, scheme, value, exp = m.groups()
            # Area is the continuation line directly below the detail row
            area = ""
            if i + 1 < len(lines):
                nxt = lines[i + 1].strip()
                if (nxt and not det_re.match(lines[i + 1]) and not item_re.match(lines[i + 1])
                        and not nxt.startswith(skip) and not (set(nxt) <= set('-'))
                        and not re.match(r'^\d{8}', nxt)
                        and re.match(r'^[A-Z0-9 ./&()\-]+\.?$', nxt)):
                    area = nxt
            rows.append([
                pcode, pname.strip(), area, cur_product, cur_pack, batch,
                bill, date, rate, qty,
                (fmark or "0"), (scheme or ""),
                (value if value is not None else ""),
            ])
            continue
        im = item_re.match(line)
        if im and not line.strip().startswith(skip):
            cur_product = im.group(2).strip()
            cur_pack = im.group(3).strip()
    return headers, rows