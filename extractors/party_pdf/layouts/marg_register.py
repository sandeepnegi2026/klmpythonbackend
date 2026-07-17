import re

from extractors.party_pdf.parse_common import _sk


def _marg_register_tail(tail):
    nums = [n.rstrip(".") for n in re.findall(r"[\d.]+", tail or "")]
    qty = nums[0] if nums else ""
    amount = nums[-1] if len(nums) >= 2 else ""
    # A glyph-scrambled export can glue a salesman's phone onto the amount
    # ("...293.05CHIRAG-9825522022"), so the trailing token is a bare 6+ digit
    # integer — never a real line amount (those carry paise decimals and are far
    # smaller). Fall back to the last decimal-bearing number, which is the amount.
    # Surgical: verified to change ONLY these phone-glued rows and leave every
    # clean marg_register file (incl. the DAHOD baselines) byte-for-byte identical.
    if amount and "." not in amount and len(amount) >= 6:
        decimals = [n for n in nums if "." in n]
        if decimals:
            amount = decimals[-1]
    s_qty = disc = sch = ""
    if len(nums) == 3:
        s_qty = nums[1]
    elif len(nums) >= 4:
        s_qty, disc = nums[1], nums[2]
        if len(nums) >= 5:
            sch = nums[3]
    return qty, s_qty, disc, sch, amount


def _marg_register_item_match(s):
    glued = re.match(
        r"^(.+?)\s+([\d.]+)([A-Z][A-Z0-9]+)\s+(\S+)\s+(\d{2}-\d{2}-\d{2})\s+(.+)$",
        s,
    )
    if glued:
        return {
            "product": glued.group(1).strip(),
            "gst": glued.group(2),
            "batch": glued.group(3),
            "inv_no": glued.group(4),
            "date": glued.group(5),
            "tail": glued.group(6),
        }
    spaced = re.match(
        r"^([\d.]+)\s+([A-Z][A-Z0-9]+)\s+(\S+)\s+(\d{2}-\d{2}-\d{2})\s+(.+)$",
        s,
    )
    if spaced:
        return {
            "product": "",
            "gst": spaced.group(1),
            "batch": spaced.group(2),
            "inv_no": spaced.group(3),
            "date": spaced.group(4),
            "tail": spaced.group(5),
        }
    inv_only = re.match(
        r"^([\d.]+)\s+(\S+)\s+(\d{2}-\d{2}-\d{2})\s+(.+)$",
        s,
    )
    if inv_only:
        return {
            "product": "",
            "gst": inv_only.group(1),
            "batch": "",
            "inv_no": inv_only.group(2),
            "date": inv_only.group(3),
            "tail": inv_only.group(4),
        }
    # Spaced GST+Batch variant (DAHOD PHARMAKON "Mf-Customer-Itemwise"): the item
    # row prints GST, Batch and InvNo as SEPARATE space-delimited tokens
    # ("ZYCOZOL-XL CREAM 5.00 HY505 SZ6253 09-05-26 2. 500.00") instead of gluing
    # the GST onto the batch. Tried LAST, so every line the three patterns above
    # already match is byte-for-byte unaffected; the required dd-mm-yy date +
    # uppercase batch token keep it off party/total/heading lines.
    spaced_prod = re.match(
        r"^(.+?)\s+([\d.]+)\s+([A-Z][A-Z0-9]+)\s+(\S+)\s+(\d{2}-\d{2}-\d{2})\s+(.+)$",
        s,
    )
    if spaced_prod:
        return {
            "product": spaced_prod.group(1).strip(),
            "gst": spaced_prod.group(2),
            "batch": spaced_prod.group(3),
            "inv_no": spaced_prod.group(4),
            "date": spaced_prod.group(5),
            "tail": spaced_prod.group(6),
        }
    return None


def _marg_register_party_parts(raw_line):
    cleaned = re.sub(r"\s+[\d.]+\s+[\d.]+\s*$", "", raw_line.strip())
    parts = [part.strip() for part in cleaned.split(",")]
    if len(parts) < 2:
        return cleaned, ""
    name = parts[0]
    area = parts[1]
    area = re.sub(r"\s+[A-Z]?\d{4,6}\s+", " ", area).strip()
    area = re.sub(r"\s+", " ", area)
    # DAHOD "NAME, - A01652 - amt amt": the 2nd comma-part is only the customer
    # code between dashes, so once the code is stripped nothing but "- -" remains.
    # Blank any area left with no letters (a real town/area always has letters);
    # a genuine area name is untouched.
    area = area.strip(" -")
    if not re.search(r"[A-Za-z]", area):
        area = ""
    return name, area


def _marg_register_party_line(s):
    if "," not in s:
        return False
    if _marg_register_item_match(s):
        return False
    if _sk(
        s,
        [
            "Item GST",
            "Sales Detail",
            "MF :",
            "Report Date",
            "Amount =",
            "DAHOD",
            "1ST FLOOR",
            "Invoice",
        ],
    ):
        return False
    if re.match(r"^\d+\.\s", s) or re.match(r"^[\d.]+\s+[\d.]+\s+[\d.]+\s*$", s):
        return False
    return bool(re.search(r"[\d.]+\s+[\d.]+\s*$", s))


def parse_marg_register(text):
    H = [
        "Party Name",
        "Area",
        "Item Name",
        "GST%",
        "Batch",
        "Inv No",
        "Date",
        "Qty",
        "S.Qty",
        "Disc%",
        "Sch Disc",
        "Amount",
    ]
    rows, cur_raw, last_product = [], "", ""
    for line in text.split("\n"):
        s = line.strip()
        if not s:
            continue
        if _marg_register_party_line(s):
            cur_raw = s
            continue
        item = _marg_register_item_match(s)
        if not item:
            continue
        product = item["product"] or last_product
        if item["product"]:
            last_product = item["product"]
        if not product:
            continue
        name, area = _marg_register_party_parts(cur_raw)
        qty, s_qty, disc, sch, amount = _marg_register_tail(item["tail"])
        rows.append(
            [
                name,
                area,
                product,
                item["gst"].rstrip("."),
                item["batch"],
                item["inv_no"],
                item["date"],
                qty,
                s_qty,
                disc,
                sch,
                amount,
            ]
        )
    return H, rows
