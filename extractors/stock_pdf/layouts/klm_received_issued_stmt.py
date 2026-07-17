import re

from extractors.stock_pdf.parse_common import _skip_line, _split_product_pack

# ---------------------------------------------------------------------------
# KLM "STOCK AND SALES STATEMENT" family (A.K. MEDICAL AGENCIES / SRI LAKSHMI
# ANNAPURNA MEDICAL AGENCIES). Two header-driven variants of one KLM export;
# both are currently mis-detected as stock_simple_7col.
#
#   VARIANT_AGE   header 'Item Name Pack Opening Received Issued Closing AGE'
#     -> 5 nums: Opening Received Issued Closing AGE (AGE ignored)
#        (a no-AGE row prints 4 nums: Opening Received Issued Closing)
#
#   VARIANT_VALUE header 'Item Name Pack Opening Received Issued Value Closing
#                          SReturn PReturn free'
#     -> Opening Received Issued Value Closing SReturn PReturn ... free.
#        Rows print 8 or 9 numbers: the ERP inserts ONE unlabeled zero column
#        between PReturn and free on the 9-number rows, so 'free' is always the
#        LAST value while the first seven columns are front-anchored.
#        (Value is the sales VALUE; qty is NEVER derived from it.)
#
# Zero cells are printed (0.00), so every product row carries a fixed trailing
# number count. We peel the trailing numbers with a LOCAL comma-tolerant token
# regex (do NOT touch the shared NUM_RE) and map columns per variant.
# ---------------------------------------------------------------------------

# Local comma-tolerant numeric token: 1,987.00 / 0.00 / -12 / 170,733.77
_NUM_TOK_RE = re.compile(r"^-?\d[\d,]*(?:\.\d{1,2})?$")


def _is_num(t):
    return bool(_NUM_TOK_RE.match(t))


def _to_f(t):
    return float(t.replace(",", ""))


def _peel_tail(s):
    """Split ``s`` into (product_text, [float, ...]) peeling the trailing numeric
    run with the local comma-tolerant token regex."""
    toks = s.split()
    tail = []
    while toks and _is_num(toks[-1]):
        tail.insert(0, _to_f(toks.pop()))
    return " ".join(toks), tail


def _is_age_header(compact):
    # 'Item Name Pack Opening Received Issued Closing AGE'
    return compact.endswith("closingage") and "openingreceivedissued" in compact


def _is_value_header(compact):
    # 'Item Name Pack Opening Received Issued Value Closing SReturn PReturn free'
    return "valueclosingsreturnpreturnfree" in compact


def _stop_line(low, compact):
    """Appended purchase-bills ledger begins here -> stop parsing entirely."""
    return "purchase bills" in low or compact.startswith("doc_date")


def _skip_row(s, low, compact):
    if _skip_line(s):
        return True
    # report grand-total / group-total footer rows
    if low.startswith("gtotal") or low.startswith("grouptotal"):
        return True
    return False


def parse_klm_received_issued_stmt(text):
    """KLM 'STOCK AND SALES STATEMENT' — AGE and Value header variants.

    AGE variant (5 nums, AGE ignored / 4 nums no-AGE):
        opening_stock, purchase_stock(Received), sales_qty(Issued), closing_stock
    Value variant (8 or 9 nums; front-anchored, free=last):
        opening_stock, purchase_stock(Received), sales_qty(Issued),
        sales_value(Value), closing_stock, sales_return(+SReturn),
        purchase_return(-PReturn), sales_free(-free, LAST value)
        identity: op + Received - Issued + SReturn - PReturn - free == Closing
    """
    records = []
    mode = None  # 'age' | 'value'
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        low = s.lower()
        compact = low.replace(" ", "")

        # appended bills ledger -> stop entirely
        if _stop_line(low, compact):
            break

        # header line switches the active variant (re-emitted on each page)
        if _is_value_header(compact):
            mode = "value"
            continue
        if _is_age_header(compact):
            mode = "age"
            continue

        if mode is None:
            continue
        if _skip_row(s, low, compact):
            continue

        prod, vals = _peel_tail(s)
        if not prod:
            continue
        # a division subtotal row prints its band name + zero movement columns
        # (e.g. 'KLM COSMO DIVISION 0.00 0.00 0.00 0.00') -> drop it
        if prod.upper().endswith("DIVISION"):
            continue

        if mode == "age":
            if len(vals) not in (4, 5):
                continue
            # 5 -> Opening Received Issued Closing AGE (ignore AGE)
            # 4 -> Opening Received Issued Closing
            opening, received, issued, closing = vals[0], vals[1], vals[2], vals[3]
            name, pack = _split_product_pack(prod)
            records.append({
                "product_name": name,
                "pack": pack,
                "opening_stock": opening,
                "purchase_stock": received,
                "sales_qty": issued,
                "closing_stock": closing,
            })
        else:  # value
            if len(vals) < 8:
                continue
            # Front-anchor the first seven columns; 'free' is the LAST value.
            # 9-number rows carry an extra unlabeled zero column between PReturn
            # and free, so this handles both 8- and 9-number rows.
            opening, received, issued, value, closing = vals[0:5]
            sreturn, preturn = vals[5], vals[6]
            free = vals[-1]
            name, pack = _split_product_pack(prod)
            records.append({
                "product_name": name,
                "pack": pack,
                "opening_stock": opening,
                "purchase_stock": received,
                "sales_qty": issued,
                "sales_value": value,
                "closing_stock": closing,
                "sales_return": sreturn,
                "purchase_return": preturn,
                "sales_free": free,
            })
    return records
