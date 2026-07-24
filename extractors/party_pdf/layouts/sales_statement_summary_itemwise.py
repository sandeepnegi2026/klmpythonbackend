import re

# ---------------------------------------------------------------------------
# "Sales Statement Summary" ITEM-primary party layout (KRISHNA SAI MEDICAL
# AGENCIES, KLM divisions COSMO / DERMA / PEDIA / PHARMA / COSMOCOR / DERMA 2).
#
# Firm band + division band ("KLM PVT LTD(COSMO)") then a report title:
#   "Sales Statement Summary from 01-06-2026 to 30-06-2026"
# Column header (un-delimited, single flat line):
#   Item Name  Party Name  Quantity  Free  Sale Amount  Tax Amount
# A stray "Quantity" echo sits on the line below the header.
#
# Each data row is a single flat line:
#   <Item Name> <Party Name> <Qty> <Free> <Sale Amount> <Tax Amount>
# with NO delimiter between Item Name and Party Name. The trailing four tokens
# are: Qty (integer or "-"), Free (integer or "-"), Sale Amount (rupee decimal),
# Tax Amount (rupee decimal). A bare "-" means nil.
#
# SPLIT RULE (item vs party): the Item Name always ends with a packing/size
# token that carries a digit (e.g. "1*10", "60ML", "30GM", "10S", "18%").
# Find the LAST such core token, then extend the pack forward over trailing
# bare unit tokens ("100 ML", "20 GMS", "10 MG") and doubled-size groups
# ("30 30GM", "20GM 20GM", "20 20", "10 MG 10 MG"). Everything up to and
# including that pack is the Item Name; the remainder (always UPPERCASE, may be
# truncated mid-word, may carry a trailing "-<TOWN>" suffix) is the Party Name.
# The "Total ... <qty> <free> <amount> <tax>" footer, the title, the company /
# division band and the ===/--- separators are skipped.
# ---------------------------------------------------------------------------

H = ["Party Name", "Product Name", "Qty", "Free", "Amount"]

# rupee decimal (Sale Amount / Tax Amount)
_MONEY = re.compile(r"^-?[\d,]+\.\d{1,2}$")
# quantity / free: a non-negative integer or a bare "-" (nil)
_QF = re.compile(r"^(?:-|\d{1,3}(?:,\d{3})*|\d+)$")

# A "core" pack token carries a digit and optionally a unit / multiplier.
# It anchors the end of the Item Name (e.g. 1*10, 60ML, 30GM, 10S, 18%, 150GMS).
_CORE = re.compile(
    r"^(?:"
    r"\d+\s*\*\s*\d+"                                  # 1*10
    r"|\d+(?:\.\d+)?%?(?:ML|GMS|GM|MG|GS|G|S|MS|M|CAPS|CAP)?"  # 60ML 30GM 10S 18% 100M 30
    r")$",
    re.I,
)
# A bare unit continuation used only to extend a pack forward (100 ML / 20 GMS).
_UNIT_ONLY = re.compile(r"^(?:ML|GMS|GM|MG|GS|G|S|MS|M|CAPS|CAP)$", re.I)


def _is_core(tok):
    return bool(_CORE.match(tok)) and any(c.isdigit() for c in tok)


def _split_item_party(prefix):
    """Split the un-delimited '<Item Name> <Party Name>' prefix."""
    toks = prefix.split()
    n = len(toks)
    last_core = -1
    for i, t in enumerate(toks):
        if _is_core(t):
            last_core = i
    if last_core < 0:
        # No pack token at all: treat the whole prefix as the product name.
        return prefix.strip(), ""
    end = last_core
    # Extend the pack forward over trailing bare units and doubled-size groups.
    j = end + 1
    while j < n:
        t = toks[j]
        if _UNIT_ONLY.match(t) or _is_core(t):
            end = j
            j += 1
            continue
        break
    item = " ".join(toks[: end + 1]).strip()
    party = " ".join(toks[end + 1:]).strip()
    return item, party


def _cast_qf(tok):
    """Qty / Free: bare '-' -> '0', otherwise the integer text."""
    return "0" if tok == "-" else tok.replace(",", "")


def parse_sales_statement_summary_itemwise(text):
    rows = []
    for raw in text.split("\n"):
        s = raw.strip()
        if not s or set(s) <= set("=-"):
            continue
        # Skip the grand-total footer ("Total <qty> <free> <amount> <tax>"). All
        # other non-data lines (firm/division bands, title, header, address,
        # separators) fail the trailing-four-token numeric gate below, so no
        # explicit band filter is needed — and none may be used, because product
        # names legitimately start with "KLM " (KLM EXTEND CAPS, KLM KLIN ...).
        if s.lower().startswith("total"):
            continue
        toks = s.split()
        if len(toks) < 6:
            continue
        # trailing four tokens: Qty, Free, Sale Amount, Tax Amount
        if not (
            _MONEY.match(toks[-1])
            and _MONEY.match(toks[-2])
            and _QF.match(toks[-3])
            and _QF.match(toks[-4])
        ):
            continue
        qty = _cast_qf(toks[-4])
        free = _cast_qf(toks[-3])
        amount = toks[-2].replace(",", "")
        prefix = " ".join(toks[:-4])
        product, party = _split_item_party(prefix)
        if not product:
            continue
        rows.append([party, product, qty, free, amount])
    return H, rows
