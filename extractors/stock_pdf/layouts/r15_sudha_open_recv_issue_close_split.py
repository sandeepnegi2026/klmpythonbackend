"""SUDHA ENTERPRISES (Ranchi, Marg ERP) "KLM PHARMA STOCK & SALES STATEMENT" —
horizontally page-split Opening / Receive / Issue / Closing statement.

The report is too wide for one page, so Marg splits every column band across two
physically separate page blocks that must be JOINED by row index (identical product
order, identical row count):

    LEFT page-block header (two rendered lines):
        PRODUCT DESCRIPTION | OPENING | OPENING | RECEIVE | RECEIVE | ISSUE
                            |  STOCK  |  VALUE  | QUANTITY| VALUE   | QUANTITY
      -> each product row = name + exactly 5 numbers:
         [OPENING_STOCK(qty), OPENING_VALUE, RECEIVE_QTY, RECEIVE_VALUE, ISSUE_QTY]
      ends with a "TOTAL <5 numbers>" grand-total row (skipped).

    RIGHT page-block header (two rendered lines, NO product names — values only):
        ISSUE | CLOSING | CLOSING | EXPIRY
        VALUE |  STOCK  |  VALUE  |  STOCK
      -> each row = [ISSUE_VALUE, CLOSING_STOCK(qty), CLOSING_VALUE, EXPIRY]
         EXPIRY renders as a date token '01-Oct-26' or a bare '- -' placeholder.
      ends with a grand-total row '<issue_val> <closing_qty> <closing_val> - -'.

The two blocks share the identical product order and row count, so RIGHT row *i*
completes LEFT row *i*.

Per-product identity (verified, 0 mismatches on the SUDHA MAY sample):
    CLOSING_STOCK = OPENING_STOCK + RECEIVE_QTY - ISSUE_QTY

Mapping (qty and value kept in separate fields — never derive qty from a value):
    opening_stock        = left[0]
    opening_value        = left[1]
    purchase_stock       = left[2]      (RECEIVE QUANTITY)
    purchase_value       = left[3]      (RECEIVE VALUE)
    sales_qty            = left[4]      (ISSUE QUANTITY)
    sales_value          = right[0]     (ISSUE VALUE)
    closing_stock        = right[1]     (CLOSING STOCK qty)
    closing_stock_value  = right[2]     (CLOSING VALUE)
    expiry               = right[3]     (EXPIRY date, blank when '- -')

Gate token (compact, spaces-stripped, lowercased) — the LEFT-page header run
'openingopeningreceivereceiveissue' plus the RIGHT-page run
'issueclosingclosingexpiry'. Both together are unique to this split export and
appear in no other stock layout (the "receipt/issue/closing" siblings spell the
column "RECEIPT", never the doubled "RECEIVE RECEIVE" here, and none carry the
bare 'ISSUE CLOSING CLOSING EXPIRY' right-page header).
"""

import re

from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_numbers,
    _split_product_pack,
)

# A right-page EXPIRY token: '01-Oct-26' style date (dd-Mon-yy) OR the '- -' blank.
_EXPIRY_DATE_RE = re.compile(r"^\d{1,2}-[A-Za-z]{3}-\d{2,4}$")
_NUM_TOK_RE = re.compile(r"^-?\d+(?:\.\d+)?$")


def parse_r15_sudha_open_recv_issue_close_split(text):
    lines = text.splitlines()

    # 1) LEFT block: product rows with exactly 5 trailing numbers.
    left = []
    for line in lines:
        s = line.strip()
        if _skip_line(s):
            continue
        prod, tail, _exp = _split_product_numbers(s)
        if not prod:
            continue
        vals = _nums(tail)
        # exactly 5 numeric cols; the TOTAL row is dropped by _skip_line (SUBTOTAL_RE)
        if len(vals) != 5:
            continue
        name, pack = _split_product_pack(prod)
        left.append(
            {
                "name": name,
                "pack": pack,
                "opening_stock": vals[0],
                "opening_value": vals[1],
                "receive_qty": vals[2],
                "receive_value": vals[3],
                "issue_qty": vals[4],
            }
        )

    # 2) RIGHT block: value-only rows = ISSUE_VALUE CLOSING_STOCK CLOSING_VALUE EXPIRY.
    #    Row shape: 3 numbers followed by a date token OR a bare '- -' placeholder.
    #    The trailing grand-total row (also 3 numbers + '- -') is trimmed by count.
    right = []
    for line in lines:
        s = line.strip()
        if not s:
            continue
        toks = s.split()
        if len(toks) < 3:
            continue
        # must start with 3 numeric cells
        if not all(_NUM_TOK_RE.match(t) for t in toks[:3]):
            continue
        rest = toks[3:]
        # what remains must be a date, a '-'/'- -' placeholder, or nothing
        expiry = ""
        if rest:
            joined = " ".join(rest)
            if _EXPIRY_DATE_RE.match(rest[0]):
                expiry = rest[0]
            elif set(rest) <= {"-"}:
                expiry = ""
            else:
                # a 4th real number (or alpha) => this is a LEFT-block/other line, skip
                if any(_NUM_TOK_RE.match(t) and t != "-" for t in rest):
                    continue
                expiry = ""
        vals = _nums(toks[:3])
        if len(vals) != 3:
            continue
        right.append(
            {
                "issue_value": vals[0],
                "closing_stock": vals[1],
                "closing_value": vals[2],
                "expiry": expiry,
            }
        )

    # Trim right to the product count (drops the trailing grand-total row).
    n = len(left)
    right = right[:n]

    records = []
    for i, l in enumerate(left):
        r = right[i] if i < len(right) else {
            "issue_value": 0.0, "closing_stock": 0.0,
            "closing_value": 0.0, "expiry": "",
        }
        rec = {
            "product_name": l["name"],
            "pack": l["pack"],
            "opening_stock": l["opening_stock"],
            "opening_value": l["opening_value"],
            "purchase_stock": l["receive_qty"],       # RECEIVE QUANTITY
            "purchase_value": l["receive_value"],      # RECEIVE VALUE
            "sales_qty": l["issue_qty"],               # ISSUE QUANTITY
            "sales_value": r["issue_value"],           # ISSUE VALUE
            "closing_stock": r["closing_stock"],       # CLOSING STOCK qty
            "closing_stock_value": r["closing_value"], # CLOSING VALUE
        }
        if r["expiry"]:
            rec["expiry"] = r["expiry"]
        records.append(rec)
    return records
