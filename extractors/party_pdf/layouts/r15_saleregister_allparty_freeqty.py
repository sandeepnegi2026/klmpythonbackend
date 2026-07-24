import re

# ---------------------------------------------------------------------------
# Marg "SALES REGISTER [ALL PARTY WITH ALL PRODUCTS]" — party-banded item-wise
# sales register with a Free-Qty / Free-Value split (BHOOLA DISTRIBUTORS, Surat;
# KLM LABORATORIES distributor).
# Source file: BHOOLA DISTRIBUTERS/Party report/QualityWiseSaleReg.pdf
#
# Exact column header (gate token, whitespace-stripped + lowercased):
#     Product Name Free Qty Free Value Qty Total Qty Amount
#     -> productnamefreeqtyfreevalueqtytotalqtyamount
#
# Page/report furniture repeats on every page:
#     BHOOLA DISTRIBUTORS                              <- vendor banner
#     SHOP.NO.109 ... KATARGAM,SURAT,395004            <- address
#     SALES REGISTER [ALL PARTY WITH ALL PRODUCTS]     <- report title
#     KLM LABORATORIES PVT LTD- --ALL--                <- company/division
#     01-06-2026 To 17-06-2026                         <- period
#     Product Name Free Qty Free Value Qty Total Qty Amount   <- column header
#
# Body nesting (one block per party):
#     BHOOLA DISTRIBUTORS - 01/06/2026 to 17/06/2026   <- per-party context line
#     AAIJEE MED & GEN.ST.[DINDOLI]                    <- PARTY band
#     SOFIBAR SNYDET BAR 0 0.00 3 3 416.94             <- product row
#     Total 0 0.00 3 3 416.94                          <- per-party subtotal (skip)
#     ...
#     Total 36 7158.24 551 587 101701.44               <- page/grand total (skip)
#     Page 1 of 9
#
# Product-row grammar — exactly FIVE trailing numbers:
#     <PRODUCT>  FreeQty  FreeValue  Qty  TotalQty  Amount
#     e.g.  MUPISOFT OINTMENT 2 165.08 10 12 825.40
#           FreeQty=2  FreeValue=165.08  Qty=10  TotalQty=12(=2+10)  Amount=825.40
# FreeQty and TotalQty are integers, Qty is an integer, FreeValue and Amount are
# 2-decimal money. TotalQty == FreeQty + Qty on every row (self-check).
#
# Field map (SACRED — qty and value never mixed):
#   PARTY band text        -> party_name / party_location (split on [..] / (..))
#   PRODUCT text           -> product_name
#   Qty  (paid qty column) -> qty            (sales_qty)
#   FreeQty                -> free_qty        (sales_free)
#   Amount                 -> amount          (sole value column)
# FreeValue and TotalQty are redundant/derived (FreeValue is the value of the
# free units; TotalQty = qty + free_qty) and are NOT emitted, so no downstream
# header maps a value column onto a quantity slot. Party sales report -> only the
# sales side exists; reconcile is qty (=Total Qty) & amount against the printed
# per-party 'Total' lines, which match to the paise on the reference file.
# ---------------------------------------------------------------------------

_MONEY = r"\d[\d,]*\.\d{2}"
_INT = r"\d[\d,]*"

# Product row: name + FreeQty(int) FreeValue(money) Qty(int) TotalQty(int) Amount(money)
_PRODUCT = re.compile(
    rf"^(?P<name>.*?\S)\s+"
    rf"(?P<freeqty>{_INT})\s+"
    rf"(?P<freeval>{_MONEY})\s+"
    rf"(?P<qty>{_INT})\s+"
    rf"(?P<totqty>{_INT})\s+"
    rf"(?P<amount>{_MONEY})\s*$"
)

# per-party subtotal & page/grand total lines: "Total 0 0.00 3 3 416.94"
_TOTAL = re.compile(r"^total\b", re.I)

# Repeating page furniture / metadata to drop (whitespace-collapsed, lowercased).
_SKIP = re.compile(
    r"^(sales\s+register\b|klm\s+laboratories\b|shop\.?no\b|"
    r"product\s+name\s+free\s+qty\b|page\s+\d+\s+of\s+\d+|"
    r"\d{2}-\d{2}-\d{4}\s+to\s+\d{2}-\d{2}-\d{4}$)",
    re.I,
)

# per-party context line: "<VENDOR> - 01/06/2026 to 17/06/2026" (drop; it anchors
# the party band that immediately follows).
_CONTEXT = re.compile(r"^.+?\s-\s\d{2}/\d{2}/\d{4}\s+to\s+\d{2}/\d{2}/\d{4}$", re.I)


def _split_party_area(raw):
    """Split a party band into (name, area).

    The area is carried inside a trailing '[...]' bracket (or, less often, a
    trailing '(..)') e.g. 'AAIJEE MED & GEN.ST.[DINDOLI]' -> ('AAIJEE MED &
    GEN.ST.', 'DINDOLI'). Names with no bracket keep the whole text and an empty
    area (e.g. 'OHM SHREE MEDICAL STORES.')."""
    s = raw.strip().rstrip(".,")
    m = re.search(r"[\[(]([^\])]+)[\])]\s*$", s)
    if m:
        name = s[: m.start()].strip().rstrip(".,")
        return name, m.group(1).strip()
    return s, ""


def parse_r15_saleregister_allparty_freeqty(text):
    headers = ["Party Name", "Area", "Product Name", "Qty", "Free", "Amount"]

    lines = [ln.strip() for ln in text.split("\n")]

    # discover the vendor banner (first non-blank line) so its recurrence can be
    # dropped along with the address line that always follows it.
    banner = ""
    for ln in lines:
        if ln:
            banner = ln
            break

    rows = []
    party_name = party_area = ""
    prev = ""
    for s in lines:
        cur_prev, prev = prev, s
        if not s:
            continue

        # vendor banner + address line (address immediately follows the banner)
        if banner and (s == banner or cur_prev == banner):
            continue
        if _SKIP.match(s):
            continue
        if _TOTAL.match(s):
            continue

        m = _PRODUCT.match(s)
        if m:
            if not party_name:
                continue
            name = m.group("name").strip()
            free = m.group("freeqty").replace(",", "")
            qty = m.group("qty").replace(",", "")
            amount = m.group("amount").replace(",", "")
            rows.append([party_name, party_area, name, qty, free, amount])
            continue

        # per-party context line -> drop (the next line is the party band)
        if _CONTEXT.match(s):
            continue

        # otherwise this is a PARTY band heading
        if re.search(r"[A-Za-z]", s):
            party_name, party_area = _split_party_area(s)

    return headers, rows
