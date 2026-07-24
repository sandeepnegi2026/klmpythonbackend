import re

# RAMESH MEDICAL "Stock statement" (Prompt ERP, bordered) — multi-division per page.
# Header run:
#   Item Name  Pack  Opening  Purchase  Sale  Closing  Rate  Stock
#   Size       Stock  Qty      Qty       Stock Value
# Each division is introduced by a "Manufacturer Name : KLM LAB. ..." band and closed
# by a "Total in Value : ..." footer. Every product row ends with SIX decimal columns:
#   Opening  Purchase  Sale  Closing  Rate  StockValue
# (rate is unit-price; StockValue is the closing-stock rupee value). There is NO Free /
# Return column, so the reconcile identity is  closing = opening + purchase - sales.
#
# The rectangle-grid parser (parse_bordered) mangles this geometry: it splits the
# "Manufacturer Name" band into phantom 'nufacturer' rows, drops ~170 of 227 products,
# and never maps the Rate/StockValue columns. The text layer is clean and column-regular,
# so a trailing-number text parse is correct.

_NUM = re.compile(r"-?\d+\.\d{1,2}$")


def parse_prompt_stock_mfr_value(text):
    records = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        low = s.lower()
        # section band / footer / page headers -> skip (E4 guard)
        if low.startswith("manufacturer name"):
            continue
        if low.startswith("total in value"):
            continue
        if low.startswith("item name") or low.startswith("size stock"):
            continue
        if low.startswith("stock statement") or low.startswith("date :") \
                or low.startswith("page :"):
            continue

        toks = s.split()
        # peel the trailing run of decimal numbers
        tail = []
        while toks and _NUM.match(toks[-1]):
            tail.insert(0, toks.pop())
        # RAMESH rows carry EXACTLY six trailing decimals
        # (op, pur, sale, close, rate, value). Require >=6 and take the LAST six
        # so a stray numeric-looking name token before pack is not consumed.
        if len(tail) < 6 or not toks:
            continue
        nums = tail[-6:]
        # everything the 6 numbers did not consume is name(+pack); if the trailing
        # count was >6 the extra leading numbers belong to the name/pack text.
        name_extra = tail[:-6]
        product = " ".join(toks + name_extra).strip()
        if not product or not re.search(r"[A-Za-z]", product):
            continue

        op, pur, sale, close, rate, value = (float(x) for x in nums)
        rec = {
            "product_name": product,
            "opening_stock": op,
            "purchase_stock": pur,
            "sales_qty": sale,
            "closing_stock": close,
            "rate": rate,
            "closing_stock_value": value,
        }
        records.append(rec)
    return records
