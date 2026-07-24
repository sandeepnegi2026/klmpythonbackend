"""RAJA ENTERPRISE converter "PARTY / ITEM WISE SALES SUMMARY" (party_xlsx).

Same "Table N" paginated converter as the RAJA/S.M. STOCK reports, but the party sales
summary: customer parties (NAME-TOWN) each followed by their item lines and a per-party
"TOTAL :", ending in a GRAND TOTAL. Columns: DESCRIPTION | (pack) | QTY | FREE | RATE |
AMOUNT | (%). Every product row ends in the same 5 numerics [QTY FREE RATE AMOUNT %].

Three physical row shapes (the 'mixed' fallback only reads the first, losing ~80% of rows):
  1. pipe/multi-cell:   CETALORE TAB | 1*10 | 5 | 0 | 48.63 | 243.16 | 0.04
  2. space-padded 1-cell: "SOFIBAR SYNDET BAR 75GR    13   0   132.57   1723.35   0.29"
  3. party glued to its first item via a newline in ONE cell:
       "A H ENTERPRISE-SHERPUR\nONITRAZ SB 130 CAP 10   4  0  166.26  665.05  0.11"

Pipeline concatenates all sheets before calling this (party pipeline's RAJA gate). Reconcile
oracle: sum(qty)=4288 and sum(amount)=595561.11 == printed GRAND TOTAL (exact, 463 rows).

A party header is a NAME-TOWN line (contains '-', has letters); the stray number cells of a
TOTAL row and the split header tokens (QTY./FREE/RATE/N/GSTIN/address) have no '-' so they are
never mistaken for parties.
"""
import re

_NUM = re.compile(r"^-?\d+(?:\.\d+)?$")
# a product line ends in: QTY(int) FREE(int) RATE(dec) AMOUNT(dec) %(dec)
_TRAIL5 = re.compile(
    r"^(.*?)\s+(-?\d+)\s+(-?\d+)\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s*$"
)
_SKIP = (
    "total", "raja", "party /", "d e s c", "company", "report for", "page no",
    "continued", "grand total", "*** end", "gstin",
)


def _num(t):
    t = t.strip().replace(",", "")
    return float(t) if _NUM.match(t) else None


def _is_skip(s):
    s = s.strip().lower()
    return any(s.startswith(k) for k in _SKIP)


def _is_party(line):
    # NAME-TOWN: has a hyphen and at least two letters; excludes bare numbers / header tokens.
    return "-" in line and sum(c.isalpha() for c in line) >= 2 and not _is_skip(line)


def _emit(records, party, town, desc, qty, free, rate, amount):
    name = desc.strip(" |")
    if not name:
        return
    records.append({
        "party_name": party or "",
        "party_location": town or "",
        "product_name": name,
        "qty": qty,
        "free_qty": free,
        "rate": rate,
        "amount": amount,
    })


def parse_raja_party_item_summary(rows):
    records = []
    party = town = ""
    for row in rows:
        cells = [c for c in row]
        ne = [c for c in cells if c.strip()]
        if not ne:
            continue

        # shape 1/2: a structured row whose last 5 numeric cells are QTY/FREE/RATE/AMOUNT/%
        if len(ne) >= 3 and not _is_skip(ne[0]):
            nums = [(i, _num(c)) for i, c in enumerate(cells)]
            nums = [(i, v) for i, v in nums if v is not None]
            if len(nums) >= 5:
                last5 = nums[-5:]
                desc = " ".join(cells[: last5[0][0]])
                _emit(records, party, town, desc,
                      last5[0][1], last5[1][1], last5[2][1], last5[3][1])
                continue

        # shape 3 (+ party headers, TOTAL rows): text, possibly multi-line in one cell
        for line in "\n".join(ne).split("\n"):
            line = line.strip()
            if not line or _is_skip(line):
                continue
            m = _TRAIL5.match(line)
            if m:
                _emit(records, party, town, m.group(1),
                      float(m.group(2)), float(m.group(3)), float(m.group(4)), float(m.group(5)))
            elif _is_party(line):
                head = line.strip().rstrip("*").strip()
                party, _, town = head.partition("-")
                party, town = party.strip(), town.strip()
    return records, {"layout": "raja_party_item_summary"}
