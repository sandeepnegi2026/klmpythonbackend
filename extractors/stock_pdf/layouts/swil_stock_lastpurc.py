"""B.M. PHARMACEUTICALS (Bhubaneswar) 'Sales & Stock Statement' — SwilERP export.

SwilERP sibling of layouts/medtraders_sales_stock_statement.py, distinguished by a
mid-band **LastPurc DATE** column sitting between the 2nd and 3rd numeric cells.

Header (two physical lines):
    PRODUCT NAME  PACKING  Op.Bal.  Receipt  LastPurc  Total  Issue  Closing  Dump
    (units row)   Qty.     Qty.     Date      Qty.     Qty.   Balance Stock

Each data line is:  <product name + pack text>  then exactly:
    Op.Bal(int)  Receipt(int)  LastPurc-date  Total(int)  Issue(int)  Closing(int)  Dump(int)
e.g.  'APPYBUSH SYRUP 1*200ML 6 12 26/06/26 18 6 12 0'
      -> Op.Bal 6, Receipt 12, [LastPurc 26/06/26], Total 18, Issue 6, Closing 12, Dump 0
The LastPurc date prints as 'dd/mm/yy' or the empty form '/ /' when there is no
last-purchase on record; negative movements occur
('AMOCLAFIX 625 TAB 1*10 39 -39 12/05/25 0 0 0 0').

MAPPING
    opening_stock  <- Op.Bal   (group 2)
    purchase_stock <- Receipt  (group 3)
    (LastPurc date  = group 4  -> ignored; not a canonical field)
    total_stock    <- Total    (group 5, printed cross-check = Op.Bal + Receipt)
    sales_qty      <- Issue    (group 6)
    closing_stock  <- Closing  (group 7)
    (Dump Stock     = group 8  -> IGNORED: it is the unsaleable SUBSET already
                                  contained in Closing Balance — folding it into
                                  purchase_return/shortage would double-count and
                                  break the reconcile. Proof: DEKTOP LOTION row
                                  0 0 [date] 0 -10 10 10 -> closing 10 already
                                  includes the dump 10.)
    sales_return = purchase_return = 0

RECONCILE (canonical, purchase_return = sales_return = 0):
    closing = opening + purchase - sales
    e.g. APPYBUSH: 6 + 12 - 6 = 12  (EXACT)
         DEKTOP:   0 + 0 - (-10) = 10  (EXACT)
    Verified 217/217 rows in BOTH the June and May files, plus the printed
    per-row cross-check Total == Op.Bal + Receipt holds 217/217.

The footer 'TOTAL ...' / 'GRAND TOTAL ...' rows carry SIX rupee-VALUE numbers and
NO date token, so they never satisfy the anchored row regex (which requires a
LastPurc date between the 2nd and 3rd numbers). Likewise the two header lines, the
company band, and the 'Powered By SwilERP' footer fail to match — no explicit
skip lists are needed. NOTE: the printed TOTAL is rupees while data rows are
quantities (May closing 437345 == June opening 437345 chain) — never reconcile
qty sums against it.
"""
import re

from extractors.stock_pdf.parse_common import _split_product_pack

# Anchored data-row regex: product/pack body, then Op.Bal + Receipt, a LastPurc
# DATE cell ('dd/mm/yy' or the empty-date form '/ /'), then Total + Issue +
# Closing + Dump. The mandatory date cell between the 2nd and 3rd numbers is what
# separates a real data row from the 6-number rupee TOTAL/GRAND TOTAL footers.
_ROW_RE = re.compile(
    r"^(?P<body>.+?)\s+(-?\d+)\s+(-?\d+)\s+"
    r"(?:\d{2}/\d{2}/\d{2}|/\s*/)\s+"
    r"(-?\d+)\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)\s*$"
)

# Broken pack spacing: '1 *50GM' -> '1*50GM' so _split_product_pack sees a whole cell.
_BROKEN_PACK_RE = re.compile(r"(\d+)\s+\*")


def parse_swil_stock_lastpurc(text, file_bytes=None):
    records = []
    for raw in (text or "").splitlines():
        s = raw.strip()
        if not s:
            continue

        m = _ROW_RE.match(s)
        if not m:
            continue

        body = m.group("body").strip()
        opening = int(m.group(2))
        receipt = int(m.group(3))
        total = int(m.group(4))
        issue = int(m.group(5))
        closing = int(m.group(6))
        # group(7) = Dump Stock — intentionally ignored (subset of closing).

        body = _BROKEN_PACK_RE.sub(r"\1*", body)
        name, pack = _split_product_pack(body)
        if not name:
            name = body

        records.append({
            "product_name": name,
            "pack": pack,
            "opening_stock": float(opening),
            "purchase_stock": float(receipt),
            "purchase_free": 0.0,
            "purchase_return": 0.0,
            "sales_qty": float(issue),
            "sales_free": 0.0,
            "sales_return": 0.0,
            "closing_stock": float(closing),
            "total_stock": float(total),
        })
    return records
