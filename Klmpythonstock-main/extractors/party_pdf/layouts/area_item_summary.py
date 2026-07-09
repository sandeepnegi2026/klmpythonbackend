import re

# "AREA / ITEM WISE SALES SUMMARY" party layout (seen from NAVKAR PHARMA exports).
# Column header is letter-spaced: "D E S C R I P T I O N QTY. FREE RATE AMOUNT ( % )".
# Area = a bare heading line; party = a line prefixed with "-"; data rows are
# "<product> qty free rate amount disc%" where qty/free may be fractional and free
# may be "-". Per-party subtotals, "TOTAL :" and "GRAND TOTAL :" lines are skipped.

_NUM = r"-?[\d,]+\.\d+"
_QF = r"-|-?[\d,]+(?:\.\d+)?"
_ROW = re.compile(rf"^(.+?)\s+({_QF})\s+({_QF})\s+({_NUM})\s+({_NUM})\s+({_NUM})\s*$")


def parse_area_item_summary(text):
    H = ["Party Name", "Area", "Product Name", "Qty", "Free", "Rate", "Amount", "Disc%"]
    rows, party, area = [], "", ""
    letterhead = next((ln.strip() for ln in text.split("\n") if ln.strip()), "")
    for raw in text.split("\n"):
        s = raw.strip()
        if not s or set(s) <= set("-"):
            continue
        if s.upper().startswith(("TOTAL", "GRAND TOTAL")):
            continue
        if s.startswith("-") and not re.match(r"^-\s*\d", s):
            party = s[1:].strip()
            continue
        m = _ROW.match(s)
        if m:
            free = "0" if m.group(3) == "-" else m.group(3).replace(",", "")
            rows.append([party, area, m.group(1).strip(),
                         m.group(2).replace(",", ""), free,
                         m.group(4).replace(",", ""), m.group(5).replace(",", ""),
                         m.group(6).replace(",", "")])
            continue
        # a bare uppercase heading with no decimal figure => area / route name
        if re.match(r"^[A-Z0-9][A-Z0-9 .&/-]*$", s) and not re.search(r"\d+\.\d", s):
            # not an area: the report title line or the letterhead firm name
            # repeated on page headers (SRI RAM PHARMA / KLM06 family)
            if re.search(r"AREA\s*/\s*ITEM\s*WISE", s) or s == letterhead:
                continue
            area = s
    return H, rows
