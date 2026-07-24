import re

# Busy/Marg "PARTY / ITEM WISE SALES SUMMARY" with the letter-spaced
# 'D E S C R I P T I O N' header and a QTY + FREE ONLY layout, i.e. the compact
# header 'D E S C R I P T I O N QTY. FREE' with NO rate/amount/value column
# (AMRITA TRADING COMPANY / KLM COSMO + COSMOCOR exports).
#
# This is the value-less sibling of ``party_item_summary_nofree`` (whose header
# is 'DESCRIPTION QTY. RATE AMOUNT'). That parser's row regex mandates two
# 2-decimal money tokens (rate + amount) which these files never carry, so it
# 0-rows them; hence this dedicated module.
#
# Structure:
#   <PARTY NAME>                      (bare band, e.g. "DR. AK GUPTA")
#       <PRODUCT ...>  QTY  FREE      (item row; FREE may be "-" -> 0)
#       ...
#   TOTAL : <qty> <free>              (per-party subtotal -> skip)
#   GRAND TOTAL : <qty> <free>        (report total -> skip)
#
# MAPPING: party_name = band text; product_name = <desc>; qty; free_qty (free,
# "-" -> 0). There is no value/amount column in the source, so nothing maps to
# rate/amount and the file reconciles on QTY only (usually AMBER — correct
# extraction, no value in source).
#
# Some rows arrive character-DOUBLED from the PDF text layer (e.g.
# 'NNIIOOSSAALLIICC 66 LLOOTTIIOONN 5500MMLL 3300 --' and 'TTOOTTAALL :: 334499 00').
# Each such line is collapsed pair-by-pair before matching so the product/qty/
# free are recovered and the doubled subtotal is still skipped. The collapse is
# gated (most tokens must be perfectly doubled) so ordinary lines are untouched.

_QTY = r"-?\d[\d,]*(?:\.\d+)?"          # qty: integer or fractional, opt sign
_FREE = r"-|-?\d[\d,]*(?:\.\d+)?"       # free: "-" or a number, opt sign
# item row: <description>  QTY  FREE   (exactly the trailing two numeric columns)
_ROW = re.compile(rf"^(?P<desc>.+?)\s+(?P<qty>{_QTY})\s+(?P<free>{_FREE})$")

# report furniture / metadata lines to drop (upper-cased, whitespace-collapsed)
_SKIP_PREFIXES = (
    "TOTAL", "GRAND TOTAL", "CONTINUED", "PARTY / ITEM", "REPORT FOR",
    "COMPANY :", "GSTIN", "PHONE", "FROM ", "D E S C R I P T I O N",
    "OUR SOFTWARE",
)


def _dedouble_token(tok):
    """Collapse a token whose every character is doubled (c0 c0 c1 c1 ...).
    Return the collapsed form, or None if the token is not perfectly doubled."""
    if len(tok) < 2 or len(tok) % 2 != 0:
        return None
    out = []
    for i in range(0, len(tok), 2):
        if tok[i] != tok[i + 1]:
            return None
        out.append(tok[i])
    return "".join(out)


def _dedouble_line(s):
    """If most whitespace-tokens on the line are perfectly doubled, collapse
    them; otherwise return the line unchanged (ordinary lines untouched)."""
    toks = s.split()
    if len(toks) < 2:
        return s
    ded = [_dedouble_token(t) for t in toks]
    doubled = sum(1 for d in ded if d is not None)
    if doubled >= max(2, (len(toks) + 1) // 2):
        return " ".join(d if d is not None else t for d, t in zip(ded, toks))
    return s


def parse_party_item_summary_qtyfree(text):
    H = ["Party Name", "Product Name", "Qty", "Free"]
    rows, party = [], ""

    for raw in text.split("\n"):
        s = re.sub(r"\s+", " ", raw.strip())
        if not s or set(s) <= set("-"):
            continue
        s = _dedouble_line(s)          # recover character-doubled lines
        su = s.upper()

        # subtotals / report metadata / column header / footer -> skip
        if su.startswith(_SKIP_PREFIXES) or "SALES SUMMARY" in su or "E-MAIL" in su:
            continue

        m = _ROW.match(s)
        if m and party:
            free = m.group("free")
            freev = "0" if free == "-" else free.replace(",", "")
            rows.append([
                party,
                m.group("desc").strip(),
                m.group("qty").replace(",", ""),
                freev,
            ])
            continue

        # otherwise a bare party heading -> becomes the current party
        if re.search(r"[A-Za-z]", s):
            party = s

    return H, rows
