import re

from extractors.stock_xlsx.parse_common import is_subtotal, to_number


def parse_html_stock_table(file_bytes):
    text = file_bytes.decode("utf-8-sig", errors="replace")
    records = []
    for block in re.finditer(
        r"<tr>\s*<td[^>]*class=\"text-start\"[^>]*>([^<]+)</td>(.*?)</tr>",
        text,
        re.I | re.S,
    ):
        product = block.group(1).strip()
        if not product or is_subtotal(product):
            continue
        nums = [to_number(v) for v in re.findall(r">([\d.]+)</td>", block.group(2))]
        nums = [n for n in nums if n is not None]
        if len(nums) < 8:
            continue
        records.append(
            {
                "product_name": product,
                "opening_stock": nums[0],
                "purchase_stock": nums[1],
                "sales_qty": nums[3],
                "sales_return": nums[4],
                "closing_stock": nums[6],
                "closing_stock_value": nums[7],
            }
        )
    detected = {
        "Product Name": "product_name",
        "Opening": "opening_stock",
        "Purchase": "purchase_stock",
        "Sale": "sales_qty",
        "ClosStock": "closing_stock",
        "Clos.Amt": "closing_stock_value",
    }
    return records, detected
