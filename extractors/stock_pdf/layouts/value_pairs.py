import re

from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_numbers,
    _split_product_pack,
)

# UNIVERSAL MEDICAL AGENCY prints the pack as a SPACE-SEPARATED token
# ('EKRAN AQUA GEL  1 * 50  295 ...') sitting between the product name and RATE.
# Because '*'/'X' is not numeric, _split_product_numbers' right-to-left tail walk
# stops at it and pulls the trailing pack digit ('50', '10', ...) into the numeric
# run, shifting every column by one (RATE read as opening-qty, opening-VALUE read
# as purchase, ...) -> 56% of rows fail stock reconciliation.
#
# Every GREEN sibling that shares this exact header instead writes the pack GLUED
# into ONE token ('1*50GR', '1X50GR', '1*10', '6*8TAB') or omits it entirely, so
# _split_product_numbers already leaves it in the product text and the columns line
# up. Collapsing ONLY the standalone spaced form '<digits> <*|X> <digits>' back into
# a single glued token reproduces the GREEN-sibling shape without touching those
# already-single-token packs: the gate ('*'/'X' with whitespace on BOTH sides)
# provably never fires on a glued pack, so rows without the spaced form are byte-
# identical to before.
_SPACED_PACK_RE = re.compile(r"(?<=\s)(\d+)\s+([*xX])\s+(\d+)(?=\s)")


def parse_value_pairs(text):
    """Marg Qty-Value Pairs: product [RATE] OPEN_QTY OPEN_VAL RECEIPT_QTY RECEIPT_VAL ISSUE_QTY ISSUE_VAL CLOSE_QTY CLOSE_VAL [DUMP] [M.EXP]"""
    records = []
    for line in text.splitlines():
        s = line.strip()
        if _skip_line(s):
            continue
        # Gate: only rewrite when the standalone spaced pack is present; glued packs
        # and pack-less rows fall through unchanged (sub() is a no-op on them).
        s = _SPACED_PACK_RE.sub(r"\1\2\3", s)
        prod, tail, exp = _split_product_numbers(s)
        if not prod or len(tail) < 8:
            continue
        name, pack = _split_product_pack(prod)
        vals = _nums(tail)
        if len(vals) < 8:
            continue
        offset = 0
        if len(vals) >= 9 and vals[0] > 0:
            offset = 1
        r = {
            "product_name": name,
            "pack": pack,
            "rate": vals[0] if offset else 0.0,
            "opening_stock": vals[offset],
            "opening_value": vals[offset + 1],
            "purchase_stock": vals[offset + 2],
            "purchase_value": vals[offset + 3],
            "sales_qty": vals[offset + 4],
            "sales_value": vals[offset + 5],
            "closing_stock": vals[offset + 6],
            "closing_stock_value": vals[offset + 7]
            if offset + 7 < len(vals)
            else 0.0,
        }
        if exp:
            r["expiry"] = exp
        records.append(r)
    return records
