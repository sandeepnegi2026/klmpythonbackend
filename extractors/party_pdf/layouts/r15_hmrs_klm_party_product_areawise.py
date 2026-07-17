import re

# ---------------------------------------------------------------------------
# HMRS PHARMA CARE LLP — KLM "Party / Product (Area Wise)" sales detail.
# Source file: HMRS PHARMA CARE LLP _ATLANTA AGEN._/Party report/
#              KLM-PARTY-PRODUCT.pdf
#
# Furniture (repeated every page):
#   "HMRS PHARMA CARE LLP"
#   "CIN No : ... GSTIN No : ..."
#   "AREA WISE"
#   "From Date : DD/MM/YYYY Upto Date : DD/MM/YYYY"
#   dashed rules "-----"
#   column header (GATE token, spaces stripped/lowercased):
#     "PCode Product Name InvNo Area City InvDate Qty Free GrsAmt
#      Manufacturer / Division"
#   page footer "Page No. N (Continuted.....) (K records) Medica Ultimate ..."
#
# Body (two levels):
#   * PARTY band  — a bare store-name line with NO leading PCode and NO date,
#     e.g. "A-ONE CHEMIST & GENERAL STORES". Carried down onto its item rows.
#   * ITEM row    — "<PCode> [<Product Name>] <InvNo> <Area> <City> <InvDate>
#                    <Qty> <GrsAmt> [<Manufacturer / Division>]".
#     PCode is a 4-6 digit product code. Product Name may be ABSENT on a
#     continuation row for the same PCode (e.g. "17370 26038 V-M THANE-W
#     04/06/2026 1 153.57" repeats the previous product code with a blank name);
#     in that case the name is carried down from the last row with the same
#     PCode. Area is a route tag ("V-M", "BM-MON/THU"), City is the town.
#   * "Total (G1) <qty> <amount>" — per-party roll-up (skipped).
#
# Numeric columns: the header lists Qty, Free, GrsAmt but the Free column is
# NEVER populated in this export — every item row prints exactly TWO trailing
# numbers before the optional Manufacturer/Division text: Qty (integer) then
# GrsAmt (amount, one decimal place). So Qty is taken as the first trailing
# integer and Amount (GrsAmt) as the decimal AFTER it — Amount is NEVER derived
# from qty. Free is emitted blank. Verified: per-party item Qty sums equal the
# printed "Total (G1) <qty>" for every band (e.g. G1=32 for A-ONE, 11 for
# AADHAR, 8 for AMBIKA SURGICAL), and item GrsAmt sums equal the printed band
# amount, so qty and value both reconcile to the source's own totals.
#
# The anchor for an item row is the trailing "<int> <decimal>" pair sitting
# right after the DD/MM/YYYY invoice date; the Manufacturer/Division text (which
# may itself contain digits inside parens, e.g. "KLM C-20") follows and is kept
# verbatim as division. Everything between the leading PCode and the InvNo is
# the Product Name.
# ---------------------------------------------------------------------------

H = [
    "Party Name",
    "Product Code",
    "Product Name",
    "Invoice No",
    "Route",
    "City",
    "Date",
    "Qty",
    "Free Qty",
    "Amount",
    "Division",
]

# Item row: leading PCode, then anything, then a DD/MM/YYYY date, then the two
# numeric columns (Qty int + GrsAmt decimal), then optional Manufacturer text.
_ITEM = re.compile(
    r"^(\d{3,7})\s+(.*?)\s+(\d{2}/\d{2}/\d{4})\s+"
    r"(\d+)\s+([\d,]+\.\d+)\s*(.*)$"
)

# Column header / chrome we must never treat as a party band.
_CHROME = (
    "PCODE PRODUCT",
    "FROM DATE",
    "AREA WISE",
    "CIN NO",
    "PAGE NO",
    "HMRS PHARMA",
    "TOTAL (G",
)


def _is_chrome(su):
    if set(su) <= set("- "):
        return True
    for k in _CHROME:
        if su.startswith(k) or k in su:
            return True
    return False


def parse_r15_hmrs_klm_party_product_areawise(text):
    rows = []
    party = ""
    last_code = ""
    last_name = ""
    for raw in text.split("\n"):
        s = re.sub(r"\s+", " ", raw.strip())
        if not s:
            continue

        su = s.upper()
        if _is_chrome(su):
            continue

        m = _ITEM.match(s)
        if m:
            code = m.group(1)
            middle = m.group(2).strip()
            invdate = m.group(3)
            qty = m.group(4)
            amount = m.group(5).replace(",", "")
            division = m.group(6).strip()

            # middle = "<Product Name?> <InvNo> <Route> <City...>"
            # Peel InvNo/route/city off the RIGHT of `middle`; InvNo is a bare
            # integer, Route is a token with a hyphen or slash, City is the rest.
            # If Product Name is absent (continuation row), middle starts with
            # the InvNo integer directly.
            mtoks = middle.split()
            name = ""
            invno = ""
            route = ""
            city = ""
            if mtoks:
                # Find the InvNo: the first PURE integer token scanning L->R
                # that begins the "<InvNo> <Route> <City>" tail. Product name
                # tokens precede it; a name token can be numeric-looking only
                # rarely, so we take the LAST pure-integer run boundary that
                # leaves a plausible route+city after it. Simpler + robust:
                # the tail is exactly the last portion "<InvNo> <Route> <City>".
                # City can be multi-word, Route is one token containing '-' or
                # '/', InvNo is the integer immediately before Route.
                route_idx = None
                for i in range(1, len(mtoks)):
                    if ("-" in mtoks[i] or "/" in mtoks[i]) and re.match(
                        r"^\d+$", mtoks[i - 1] or ""
                    ):
                        route_idx = i
                        break
                if route_idx is not None:
                    invno = mtoks[route_idx - 1]
                    route = mtoks[route_idx]
                    city = " ".join(mtoks[route_idx + 1:]).strip()
                    name = " ".join(mtoks[: route_idx - 1]).strip()
                else:
                    # Fallback: InvNo is the last pure-integer, everything before
                    # it is the name; no clean route/city split.
                    name = middle

            if not name:  # continuation row -> carry product name for this code
                if code == last_code:
                    name = last_name
            else:
                last_code, last_name = code, name

            if not party:
                continue
            rows.append([
                party,
                code,
                name,
                invno,
                route,
                city,
                invdate,
                qty,
                "",           # Free never populated
                amount,
                division,
            ])
            continue

        # A bare line with letters and no leading PCode/date -> party band.
        if re.search(r"[A-Za-z]", s) and not re.match(r"^\d", s):
            party = s

    return H, rows
