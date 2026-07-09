import re

from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_pack,
    _to_number,
)


def parse_pharma_bytes_itemcode(text):
    """Pharma Bytes Item-Code: Item Name + 6-digit Code + Packing + Op/Rcvd/Issue/Close/Exp numbers."""
    records = []
    division = ""
    for line in text.splitlines():
        s = line.strip().replace("`", "")
        if _skip_line(s):
            continue
        if re.match(r"^KLM\s", s, re.I):
            division = s
            continue
        if re.match(
            r"^(MFG\d|Op\. Value|Clo\. Value|Sales Value|Report Date|Page|SOURABH)",
            s,
            re.I,
        ):
            continue
        s = re.sub(r"(\D)(\d{6})(?=\s|\D|$)", r"\1 \2 ", s)
        m = re.search(r"\b(\d{6})\b", s)
        if not m:
            continue
        left = s[: m.start()].strip()
        right = s[m.end() :].strip()
        nums = _nums(right.split())
        tokens = left.split()
        if tokens and nums and _to_number(tokens[-1]) == nums[0]:
            pack = tokens[-1]
            name = " ".join(tokens[:-1])
            nums = nums[1:]
        else:
            name, pack = _split_product_pack(left)
        if len(nums) >= 5 and pack and abs(nums[0] - (_to_number(pack) or -1)) < 0.01:
            nums = nums[1:]
        if len(nums) < 2:
            continue
        record = {
            "product_name": name,
            "pack": pack,
            "product_code": m.group(1),
            "division": division,
            "opening_stock": nums[0],
            "purchase_stock": nums[1] if len(nums) > 1 else 0.0,
            "sales_qty": nums[2] if len(nums) > 2 else 0.0,
            "closing_stock": nums[3] if len(nums) > 3 else nums[-1],
        }
        records.append(record)
    return records
