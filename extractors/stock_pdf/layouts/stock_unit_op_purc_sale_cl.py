from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_numbers,
    _split_product_pack,
)

# The "Unit" column values printed by this Marg export (METRO MEDICAL AGENCIES,
# "Stock and Sales Statement", header 'Product Name Unit Pack desc Op Purc Sale
# Cl qty'). These are packaging-unit words that sit between the product name and
# the 4 numeric columns. They must be peeled off the product text so they do not
# pollute the name; a purely-alphabetic allowlist is used so a BLANK-unit row
# whose last name token is a pack/strength ('15TAB', '10ML') is left intact for
# the downstream pack peel.
_UNIT_TOKENS = {
    "PCS", "BOTT", "BOTTLE", "STRI", "STR", "TUBE", "TUB", "SYP", "PSC",
    "BOX", "KIT", "NOS", "NO", "PES", "PACK", "PKT", "JAR", "VIAL", "AMP",
    "CAN", "PAIR", "SET", "ROLL", "BAG", "PC", "EA",
}


def parse_stock_unit_op_purc_sale_cl(text):
    """Marg 'Stock and Sales Statement' — Product Name | Unit | Pack desc | Op |
    Purc | Sale | Cl qty (METRO MEDICAL AGENCIES). Exactly four QTY columns per
    row (opening / purchase / sales / closing); every zero cell is printed, so the
    trailing-4-number pop is exact. There are NO value columns — never derive a
    value from these. A trailing packaging-unit word (PCS/BOTT/STRI/TUBE/...) is
    the 'Unit' column and is stripped from the name; the remaining 'Pack desc'
    stays in the product text for the pipeline's pack peel.
    Reconcile: closing = opening + purchase - sales.
    """
    records = []
    for line in text.splitlines():
        s = line.strip()
        low = s.lower()
        if low.startswith("product name") or _skip_line(s):
            continue
        prod, tail, _ = _split_product_numbers(s)
        if not prod:
            continue
        vals = _nums(tail)
        # Exactly the 4 qty columns; use the LAST four so any stray leading token
        # that read as numeric cannot shift the movement columns.
        if len(vals) < 4:
            continue
        op, pu, sa, cl = vals[-4], vals[-3], vals[-2], vals[-1]

        toks = prod.split()
        # Peel the 'Unit' column: a trailing purely-alphabetic packaging-unit word.
        # BLANK-unit rows end in a pack/strength token ('15TAB','10ML') which is NOT
        # in the allowlist, so it is preserved for the downstream pack peel.
        if len(toks) >= 2 and toks[-1].upper() in _UNIT_TOKENS:
            toks = toks[:-1]
        name_pack = " ".join(toks).strip()
        if not name_pack:
            continue
        name, pack = _split_product_pack(name_pack)

        records.append(
            {
                "product_name": name,
                "pack": pack,
                "opening_stock": op,
                "purchase_stock": pu,
                "sales_qty": sa,
                "closing_stock": cl,
            }
        )
    return records
