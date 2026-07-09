import re

from extractors.party_pdf.parse_common import _sk


def _extract_marg_area_token(text):
    text = (text or "").strip()
    if not text:
        return ""
    first_token = text.split()[0]
    m = re.match(r"^([A-Z]{4,})S[A-Z]{1,2}\d", first_token, re.I)
    if m:
        return m.group(1).upper()
    m = re.match(r"^([A-Z]{4,})SZ\d", first_token, re.I)
    if m:
        return m.group(1).upper()
    if re.fullmatch(r"[A-Z]{3,}", first_token):
        return first_token
    m = re.match(
        r"^([A-Z]{4,}?)(?:[A-Z]{1,3}\d|[A-Z]{2}\d{3,}|\d+[A-Z]\d+)", first_token
    )
    if m:
        return m.group(1)
    m = re.match(r"^([A-Z]{3,})", first_token)
    return m.group(1) if m else ""


def _marg_register_itemwise_party_parts(head):
    head = (head or "").strip()
    if not head:
        return "", ""
    if "," in head:
        left, right = [part.strip() for part in head.split(",", 1)]
    else:
        left, right = head, ""

    area_right = _extract_marg_area_token(right)
    area_hyphen = ""
    name = left
    _JUNK_SUFFIX = {"BUS", "PRO", "ST", "STORE"}
    if "-" in left:
        idx = left.rfind("-")
        suffix = left[idx + 1 :].strip()
        candidate = _extract_marg_area_token(suffix)
        if candidate and len(candidate) >= 4 and candidate not in _JUNK_SUFFIX:
            area_hyphen = candidate
            name = left[:idx].strip()

    if area_hyphen and area_right:
        prefix_len = min(4, len(area_hyphen), len(area_right))
        area = (
            area_right
            if area_right[:prefix_len] == area_hyphen[:prefix_len]
            else area_hyphen
        )
    else:
        area = area_hyphen or area_right

    if area_right and not area_hyphen and "-" in left:
        name = left[: left.rfind("-")].strip()
    return name, area


def parse_marg_register_itemwise(text):
    H = [
        "Party Name",
        "Area",
        "Product Name",
        "Date",
        "Qty",
        "Free",
        "Rate",
        "MRP",
        "Amount",
    ]
    rows, cur_product = [], []
    prod_pat = re.compile(
        r"^([A-Z0-9][A-Z0-9\s\-./]+?)\s+\d+(?:\.\d+)?\s+\d+(?:\.\d+)?\s+\d+(?:\.\d+)?\s+[\d.]+\s*$"
    )
    skip_pf = [
        "Sales Detail",
        "Customer Batch",
        "MF :",
        "Invoice",
        "Report Date",
        "Amount =",
        "Page",
        "AAGAM",
        "1ST FLOOR",
        "Licence",
    ]
    for line in text.split("\n"):
        s = line.strip()
        if not s or _sk(s, skip_pf):
            continue
        if re.match(r"^\d+\.\s+Invoice", s):
            continue
        if prod_pat.match(s) and "," not in s:
            cur_product = re.sub(
                r"\s+\d+(?:\.\d+)?\s+\d+(?:\.\d+)?\s+\d+(?:\.\d+)?\s+[\d.]+\s*$",
                "",
                s,
            ).strip()
            continue
        if not cur_product or "," not in s:
            continue
        dm = re.search(r"(\d{2}-\d{2}-\d{2})\s+(.+)$", s)
        if not dm:
            continue
        tail = dm.group(2)
        head = s[: dm.start()].strip()
        nums = [n.rstrip(".") for n in re.findall(r"[\d.]+", tail)]
        if len(nums) < 3:
            continue
        qty = nums[0]
        amount = nums[-1]
        if len(nums) >= 5:
            free = nums[1]
            rate = nums[-3]
            mrp = nums[-2]
        elif len(nums) == 4:
            free = "0"
            rate = nums[-3]
            mrp = nums[-2]
        else:
            free = "0"
            rate = nums[1]
            mrp = ""
        name, area = _marg_register_itemwise_party_parts(head)
        rows.append(
            [name, area, cur_product, dm.group(1), qty, free, rate, mrp, amount]
        )
    return H, rows
