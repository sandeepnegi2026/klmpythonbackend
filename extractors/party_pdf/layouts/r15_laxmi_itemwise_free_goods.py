import re

# LAXMI DISTRIBUTORS "Itemwise Sales Details" / "PARTY WISE FREE GOODS".
# Gate token (compact, lowercased, spaces stripped): the glyph-corrupted
# column-header run "bielxlpdntobilldtsm" (rendered header line:
# "BiElxlp DNto BillDt SM Party Code & Name Batch No Rate Qnty Free Scheme
# Value"). This corruption artifact is unique to this vendor's PDF and does
# NOT appear in the existing rp_pharma_itemwise format (which shares the
# generic title "Itemwise Sales Details" + "Party Code & Name" but uses a
# clean "Bill No" header and NxM pack bands like "1X30ML").
#
# Structure:
#   Division band : "184 KLM LAB- COSMOCOR DIV"      (code + text containing DIV)
#   Item band     : "5809 EPISERT CREAM 30 GM 30 gm" (item code + product name+pack)
#   Detail line   : <BillNo(8d)> <BillDt> <SM> <PartyCode(5d)> <PartyName>
#                   <Batch> <Rate> <Qnty> [F|Z [SchemeQty]] [Value] <exp mm/yy>
#   Item Total / Final Total lines are subtotals -> skipped.
#
# Column mapping (qty and value are separate, mapped by exact header slot):
#   Qnty   -> Qty          (sold quantity)
#   Scheme -> Free         (free / scheme quantity; the F/Z letter is the marker)
#   Value  -> Amount       (value column; absent when Qnty == 0)


def parse_laxmi_itemwise_free_goods(text):
    headers = ["Division", "Item Code", "Product Name",
               "Party Code", "Party Name", "Batch",
               "Inv No", "Date", "Rate", "Qty", "Free", "Amount"]
    rows = []
    lines = text.splitlines()

    # detail: bill(8d) date(dd/mm/yy) sm party-code(4-6d) party-name batch
    #         rate qty [F|Z [scheme]] [value] expiry(mm/yy)
    det_re = re.compile(
        r'^\s*(\d{8})\s+(\d{2}/\d{2}/\d{2})\s+(\d{1,3})\s+(\d{4,6})\s+'  # bill date sm pcode
        r'(.+?)\s+(\S+)\s+'                                              # pname batch
        r'([\d.]+)\s+(\d+)'                                             # rate qty
        r'(?:\s+([FZ])(?:\s+(\d+))?)?'                                  # opt free-marker + scheme qty
        r'(?:\s+([\d.]+))?'                                             # opt value (absent when qty=0)
        r'\s+(\d{2}/\d{2})\s*$')                                        # expiry
    # division band: code + text containing DIV (case-insensitive)
    div_re = re.compile(r'^\s*(\d{1,4})\s+(.*(?:DIV|div).*)$')
    # item band: item code (3-6 digits) + product name (fallback, after div/detail excluded)
    item_re = re.compile(r'^\s*(\d{3,6})\s+(.+)$')

    skip = ("Item Total", "Final Total", "LAXMI DISTRIBUTORS",
            "Print Date", "No.", "BiElxlp", "Page")

    cur_div = ""
    cur_code = ""
    cur_prod = ""

    for raw in lines:
        line = raw.rstrip()
        ls = line.strip()
        if not ls or set(ls) <= set('-'):
            continue
        if ls.startswith(skip):
            continue

        m = det_re.match(line)
        if m:
            (bill, date, sm, pcode, pname, batch, rate, qty,
             fmark, scheme, value, exp) = m.groups()
            rows.append([
                cur_div, cur_code, cur_prod,
                pcode, pname.strip(), batch,
                bill, date, rate, qty,
                (scheme if scheme is not None else "0"),
                (value if value is not None else ""),
            ])
            continue

        dm = div_re.match(ls)
        if dm:
            cur_div = ls
            continue

        im = item_re.match(ls)
        if im:
            cur_code = im.group(1)
            cur_prod = im.group(2).strip()

    return headers, rows
