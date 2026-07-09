import re


def parse_party_item_wise_summary(text):
    """Busy/Tally 'PARTY / ITEM WISE SALES SUMMARY' with the letter-spaced
    'D E S C R I P T I O N' header and a NO-FREE column layout, i.e.
    'D E S C R I P T I O N QTY. RATE AMOUNT' or '... QTY. RATE AMOUNT ( % )'.
    Structure: bare party heading line, then product rows, then 'TOTAL :' /
    'GRAND TOTAL :' per block. A product row is
    '<desc> <qty> [<free>] [<unit-word>] <rate> <amount> [<disc%>]' where qty/free
    may be fractional or negative, free may be '-', and a unit token (PCS, CAP,
    GEL, STRP, "S'", Pcs ...) may sit between qty/free and rate. Amount maps to
    the canonical amount field; the party name (a bare heading) is injected into
    every row.
    """
    H = ["Party Name", "Product Name", "Qty", "Free", "Rate", "Amount", "Disc%"]
    rows, party = [], ""

    NUM = r"-?[\d,]+\.\d{2}"          # money: rate / amount (2 decimals, opt sign)
    QTY = r"-?[\d,]+(?:\.\d+)?"       # qty / free: int or fractional, opt sign
    UNIT = r"[A-Za-z][A-Za-z.']*"     # unit token: PCS, CAP, GEL, STRP, Pcs, S' ...
    ROW = re.compile(
        r"^(?P<desc>.+?)\s+(?P<qty>" + QTY + r")\s+"
        r"(?:(?P<free>-|" + QTY + r")\s+)?(?:(?P<unit>" + UNIT + r")\s+)?"
        r"(?P<rate>" + NUM + r")\s+(?P<amt>" + NUM + r")(?:\s+(?P<disc>" + QTY + r"))?$"
    )

    for raw in text.split("\n"):
        s = re.sub(r"\s+", " ", raw.strip())
        if not s or set(s) <= set("-"):
            continue
        su = s.upper()
        # subtotal / grand-total / pagination lines
        if su.startswith(("TOTAL", "GRAND TOTAL", "CONTINUED")) or "PAGE NO" in su:
            continue
        # report metadata / column header lines
        if ("SALES SUMMARY" in su
                or su.startswith(("REPORT FOR", "COMPANY :", "GSTIN", "PHONE", "FROM "))
                or "E-MAIL" in su
                or "D E S C R I P T I O N" in s):
            continue

        m = ROW.match(s)
        if m and party:
            free = m.group("free")
            freev = "0" if (free is None or free == "-") else free.replace(",", "")
            rows.append([
                party,
                m.group("desc").strip(),
                m.group("qty").replace(",", ""),
                freev,
                m.group("rate").replace(",", ""),
                m.group("amt").replace(",", ""),
                (m.group("disc") or "").replace(",", ""),
            ])
            continue

        # otherwise a bare party heading -> becomes the current party
        if re.search(r"[A-Za-z]", s):
            party = s

    return H, rows