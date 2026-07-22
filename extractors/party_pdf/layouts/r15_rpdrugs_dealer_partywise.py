import re

# ---------------------------------------------------------------------------
# R.P.DRUGS & SURGICALS (Guwahati) — KLM "party wise" dealer sales statement.
# Source file: R. P. DRUGS _ SURGICAL/Party report/klmpartywise.pdf
#
# There is NO column-header row in this export (only dashed rules), so the
# format is recognised structurally by its banner + period line + dealer bands:
#
#     R.P.DRUGS & SURGICALS
#     S.C.GOSWAMI ROAD,PAN BAZAR,GUWAHATI-1            PgNo: 1
#     Dealer:ADITYA PHARMA:PAN BAZAR GHY-1             <- band header
#     w.e.f.01/05/26 to 31/05/26                       <- period line  (GATE)
#     --------------------------------------------------------------
#     --------------------------------------------------------------
#     1:EKRAN SOFT SILICONE 50 SUNSCRE50GM  484.34  0.00   1N        <- item
#     2:NEVLON CREAM (V)100GM                191.36  0.00   1N        <- item
#     --------------------------------------------------------------
#     TOTAL (2)                             675.70  0.00   2N        <- band total
#     --------------------------------------------------------------
#     Dealer:AURA MEDICOS:DIBRUGARH
#     ...
#     TOTAL (1)                             2093.09 325048.23 2N     <- report grand
#
# Row grammar (single visual line):
#     <serial>:<PRODUCT+PACK>  <VALUE_1>  <VALUE_2>  <QTY>N
# The report carries TWO value columns and ONE quantity column (units, suffixed
# "N"). Per dealer block the item rows sum EXACTLY to the "TOTAL (k)" line for
# both value columns AND the qty (verified on every block), and the grand
# totals (col1 2093.09, col2 325048.23) match the trailing "TOTAL (1) ... 2N"
# footer. The two value columns are MUTUALLY EXCLUSIVE per row for all but two
# lines (a dealer's rows populate EITHER column, e.g. ADITYA PHARMA / DEY'S
# PHARMACY report entirely in VALUE_1 with VALUE_2 = 0.00, while 16 dealers
# report entirely in VALUE_2); the single "N" quantity is the units for whichever
# value is present. So the row VALUE = VALUE_1 + VALUE_2 (grand ₹327141.32,
# dominated by VALUE_2 ₹325048.23) and the qty is the printed "N" — never
# derived. Mapping only VALUE_2 would wrongly zero the VALUE_1 dealers' amounts.
#
# Field map:  Dealer band -> party_name / party_location (name:area on colon);
#   product text (serial stripped) -> product_name (pack tail kept);
#   QTY (the "N" column) -> qty  (NEVER derived from a value);
#   VALUE_1 + VALUE_2 -> amount.  No rate/free column exists.
# ---------------------------------------------------------------------------

H = ["Party Name", "Area", "Product Name", "Qty", "Amount"]

# item:  "<serial>:<name...> <v1> <v2> <qty>N"
_ITEM = re.compile(
    r"^\s*\d+:(.+?)\s+(-?[\d,]+\.\d+)\s+(-?[\d,]+\.\d+)\s+(-?\d+)N\s*$"
)
_DEALER = re.compile(r"^\s*Dealer:(.*)$", re.I)
_TOTAL = re.compile(r"^\s*TOTAL\s*\(\d+\)", re.I)


def _split_dealer(rest):
    """'ADITYA PHARMA:PAN BAZAR GHY-1' -> ('ADITYA PHARMA', 'PAN BAZAR GHY-1').

    The band prints '<NAME>:<AREA>'. Split on the FIRST colon; if there is no
    colon the whole string is the name."""
    rest = rest.strip()
    if ":" in rest:
        name, area = rest.split(":", 1)
        return name.strip(), area.strip()
    return rest, ""


def parse_r15_rpdrugs_dealer_partywise(text):
    rows = []
    party = ""
    area = ""
    for raw in text.splitlines():
        s = raw.strip()
        if not s or set(s) <= {"-"}:
            continue

        md = _DEALER.match(s)
        if md:
            party, area = _split_dealer(md.group(1))
            continue

        if _TOTAL.match(s):
            # per-band / grand total line: not emitted
            continue

        mi = _ITEM.match(s)
        if not mi:
            continue

        name = mi.group(1).strip()
        v1 = float(mi.group(2).replace(",", ""))
        v2 = float(mi.group(3).replace(",", ""))
        amount = v1 + v2                    # mutually-exclusive value columns
        qty = mi.group(4)                   # "N" units column -> qty
        if not party or not name:
            continue
        rows.append([party, area, name, qty, "%.2f" % amount])

    return H, rows
