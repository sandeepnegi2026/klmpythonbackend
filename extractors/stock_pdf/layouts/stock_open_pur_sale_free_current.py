import re

from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_numbers,
    _split_product_pack,
)

# Trailing "E" short-expiry flag (header: "*** E = Short Expiry"). It sits after all
# numbers, so strip it before number splitting or the row is dropped.
_E_FLAG_RE = re.compile(r"\s+E\s*$")


def _strip_serial_code(prod):
    """Drop the leading "Sr." serial and the "Code" column, leaving the item name.

    The Code column always contains a digit (e.g. DEKT0001, 055123, EXTE0011) and may
    itself span tokens (e.g. "I EX0001", "KLM 0007"). Item names start with an
    alphabetic token, so strip leading tokens up to and including the first one that
    contains a digit — that consumes the whole code, single- or multi-token.
    """
    toks = prod.split()
    if toks and toks[0].isdigit():
        toks = toks[1:]  # Sr. serial
    i = 0
    while i < len(toks) and not any(c.isdigit() for c in toks[i]):
        i += 1
    # only strip the code if at least one name token remains after it
    if i < len(toks) - 1:
        toks = toks[i + 1:]
    return " ".join(toks)


def parse_stock_open_pur_sale_free_current(text):
    """KLM 'Stock and Sales Statement': Sr | Code | Item Name | Packing | Opening |
    Purchase | Sale | Free | Current | Sales Amount | Closing.

    The 7 numeric columns are Opening, Purchase, Sale, Free, **Current Stock** (the
    real closing QTY: opening + purchase - sale - free), Sales Amount (sales value),
    and Closing (the closing VALUE). The generic stock_simple_7col parser mis-reads
    closing_stock <- Sales Amount here, so this layout owns it.
    """
    records = []
    for line in text.splitlines():
        s = line.strip()
        if _skip_line(s):
            continue
        short_expiry = bool(_E_FLAG_RE.search(s))
        s = _E_FLAG_RE.sub("", s)
        prod, tail, exp = _split_product_numbers(s)
        if not prod:
            continue
        vals = _nums(tail)
        if len(vals) < 7:
            continue
        vals = vals[-7:]  # guard against a stray leading number in the tail
        name, pack = _split_product_pack(_strip_serial_code(prod))
        r = {
            "product_name": name,
            "pack": pack,
            "opening_stock": vals[0],
            "purchase_stock": vals[1],
            "sales_qty": vals[2],
            "sales_free": vals[3],       # Free goods given (outflow)
            "closing_stock": vals[4],    # "Current Stock" = real closing qty
            "sales_value": vals[5],      # "Sales Amount"
            "closing_stock_value": vals[6],
        }
        if short_expiry:
            r["short_expiry"] = True
        if exp:
            r["expiry"] = exp
        records.append(r)
    return records
