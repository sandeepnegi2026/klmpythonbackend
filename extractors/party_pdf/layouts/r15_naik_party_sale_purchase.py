import re

# ---------------------------------------------------------------------------
# NAIK AGENCIES "PARTY WISE SALE/PURCHASE REPORT" — WEP-style challan/bill
# item register, banded by party.  One vendor, monospaced fixed-column PDF.
#
# Page furniture:
#     Page No:- <n>
#     NAIK AGENCIES
#     PARTY WISE SALE/PURCHASE REPORT
#     PERIOD FROM 01-05-26 TO 31-05-26
#     ==== rule ====
#     <--- CHALLAN ---> <---- BILL ----->
#     DATE NO. DATE NO. PRODUCT CODE/ NAME PACKING BATCH NO. EXP.DT. QTY FREE RATE AMOUNT
#     ==== rule ====
#
# A party band opens with a code+name heading and an address continuation line,
# then item rows, then a "*** PARTY TOTAL ***" footer:
#     ** 2006 ANKUR MEDICAL STORE          <- party heading (numeric code + name)
#     NEAR S.T.DEPOT,CHAR POOL,            <- address continuation (skipped)
#     30-05-26 2001 30-05-26 1056 01290001 NIOSOL OINT 30GM AF602 12/2027 1 0 150.00 150.00
#     ...
#     *** PARTY TOTAL *** 9 0 1746.42     <- band footer (skipped, triage only)
#
# ITEM ROW columns (space separated, monospaced):
#   <CH-DATE dd-mm-yy> <CH-NO> <BILL-DATE dd-mm-yy> <BILL-NO> <8-digit CODE>
#   <PRODUCT NAME + PACKING ...> <BATCH> <EXP mm/yyyy> <QTY int> <FREE int>
#   <RATE money> <AMOUNT money>
#
# Right-anchored parse (the only reliable strategy — NAME+PACKING has no
# delimiter): peel AMOUNT, RATE, FREE, QTY, EXP(mm/yyyy), BATCH from the end;
# the 8-digit product code + the CHALLAN/BILL date-no quad anchor the left.
# Everything between the code and the batch is NAME+PACKING (kept together as
# product_name, pack tail left in the name, matching sibling WEP layouts).
#
# Field map (exact-header): DATE(bill)->invoice_date, NO.(bill)->invoice_number,
# PRODUCT CODE->product code, NAME->product_name, PACKING->pack, BATCH NO.->
# batch_no, EXP.DT.->expiry, QTY->qty, FREE->free_qty, RATE->rate,
# AMOUNT->amount.  qty is NEVER derived from a value; AMOUNT reconciles as
# QTY*RATE in the source (free-goods rows print qty 0 / amount 0.00).
# ---------------------------------------------------------------------------

# Row anchored on the right: <8-digit code> <name+pack> <batch> <exp> <qty> <free>
# <rate> <amount>, prefixed by the challan/bill "dd-mm-yy no dd-mm-yy no" quad.
_ITEM = re.compile(
    r"^(\d{2}-\d{2}-\d{2})\s+(\S+)\s+(\d{2}-\d{2}-\d{2})\s+(\S+)\s+"      # challan date/no, bill date/no
    r"(\d{8})\s+"                                                          # product code (8 digits)
    r"(.+?)\s+"                                                            # name + packing
    r"(\S+)\s+"                                                            # batch no
    r"(\d{1,2}/\d{4})\s+"                                                  # exp mm/yyyy
    r"(\d+)\s+(\d+)\s+"                                                    # qty, free
    r"(-?[\d,]+\.\d{2})\s+(-?[\d,]+\.\d{2})$"                              # rate, amount (signed for sales returns)
)

# Party heading: "** <numeric code> <NAME>".
_PARTY = re.compile(r"^\*+\s*(\d+)\s+(.+?)\s*$")

# Packing tail to peel from the product name into `pack` (e.g. "30GM", "100ML",
# "1X10", "1X5", "50ML").  Trailing pack token only; if none, leave name whole.
_PACK_TAIL = re.compile(r"(?:\d+X\d+|\d+(?:\.\d+)?\s*(?:ML|GM|GMS|G|MG|KG|L))$", re.I)


def _peel_pack(name):
    """Split a trailing pack token off the product name (e.g.
    'NIOSOL OINT 30GM' -> ('NIOSOL OINT', '30GM')).  Conservative: only a clear
    trailing unit/pack token is peeled; otherwise the whole string is kept and
    pack is blank."""
    n = name.strip()
    m = _PACK_TAIL.search(n)
    if m:
        pack = m.group(0).strip()
        head = n[: m.start()].strip()
        if head:
            return head, pack
    return n, ""


def parse_naik_party_sale_purchase(text):
    text = re.sub(r"\(cid:\d+\)", "", text)
    H = [
        "Party Name",
        "Product Code",
        "Product Name",
        "Packing",
        "Batch No",
        "Exp Date",
        "Bill Date",
        "Bill No",
        "Qty",
        "Free",
        "Rate",
        "Amount",
    ]
    rows = []
    party = ""
    for raw in text.split("\n"):
        s = raw.strip()
        if not s:
            continue
        low = s.lower()
        if low.startswith(("page no", "party total", "*** party total")):
            continue
        if "party total" in low:
            continue
        m = _ITEM.match(s)
        if m:
            (ch_date, ch_no, bill_date, bill_no, code, name,
             batch, exp, qty, free, rate, amt) = m.groups()
            pname, pack = _peel_pack(name.strip())
            rows.append([
                party,
                code,
                pname,
                pack,
                batch,
                exp,
                bill_date,
                bill_no,
                qty,
                free,
                rate.replace(",", ""),
                amt.replace(",", ""),
            ])
            continue
        pm = _PARTY.match(s)
        if pm:
            # A party heading is "** <code> <NAME>" and never carries the money
            # tail an item row does; the item regex already failed above, so any
            # remaining "**"-prefixed numeric-code line is a party heading.
            party = pm.group(2).strip()
    return H, rows
