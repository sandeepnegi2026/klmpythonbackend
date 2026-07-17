import re

# ---------------------------------------------------------------------------
# KLM "Item-wise Customer-wise Offtake" party layout
# (NEW SHAKTI DISTRIBUTORS, B.S. CITY / Bokaro — KLM Laboratories distributor).
# Source: NEW SHAKTI DISTRIBUTOR/Party report/KLM PARTY WISE SALES JUNE 2026.pdf
#
# Report furniture (repeats on every page):
#   NEW SHAKTI DISTRIBUTORS                              <- vendor banner
#   KUNWAR SINGH COLONY, GANDHI PATH, CHAS - 827013      <- address
#   B.S. CITY
#   Item-wise Customer-wise Offtake                      <- report title
#   Accounting Period From 01/06/2026 to 30/06/2026 Page No :1
#   01/04/2026 to 31/03/2027
#   Mfg/Mkt Company
#   Item description                                Total   <- header line 1
#   Bonus Quantity Rate Amount Amount                       <- header line 2
#
# Exact column-header gate token (whitespace-stripped, lowercased), taken from
# the two contiguous header lines:
#   itemdescriptiontotalbonusquantityrateamountamount
#
# Body nesting (Company -> Product -> Customer rows -> Product subtotal):
#   KLM-COSMO                                            <- COMPANY / division band
#   EKRAN AQUA GEL (TUB)                                 <- PRODUCT band
#   NEW BHARAT MEDICAL HALL      2.000 277.97 555.94 629.77   <- customer row
#   BHARAT MEDICAL HALL(4)       1.000 277.97 277.97 314.88   <- customer row
#                                3.000 277.97 833.91 944.65   <- PRODUCT subtotal (skip)
#   ...
#   Total Figures :-                    4234.47 4444.48       <- COMPANY subtotal (skip)
#
# Every value line carries EXACTLY four numeric tokens:
#     <Quantity> <Rate> <Amount> <TotalAmount>
# The Bonus column in the header is never populated (blank in the data), so it
# is not read. A handful of customer rows carry a trailing pack token between
# the name and the numbers, e.g.:
#     NEW BHARAT MEDICAL HALL 10/1 5.000 160.71 803.55 809.99
#     BLOSSOMS MEDICAL JODHADIH MORE CHAS 20/2 1.000 154.08 154.08 161.79
# -> a bare  d+/d+  token immediately before the numbers is a pack marker and is
# stripped off the customer name.
#
# A PRODUCT-subtotal line is a value line whose FIRST token is numeric (no
# customer text precedes the numbers); those are dropped (they only sum the
# rows above). Customer rows have leading alpha text.
#
# Field map (SACRED — qty and value are never mixed):
#   COMPANY band          -> division
#   PRODUCT band          -> product_name
#   Customer text         -> party_name
#   Quantity  (col 1)     -> qty        (sales_qty)
#   Rate      (col 2)     -> rate
#   Amount    (col 3)     -> amount     (== Quantity * Rate, the taxable value)
# The 4th column ("Total") is the tax-inclusive grand amount and is redundant
# with Amount for reconcile; it is NOT emitted, so no value column ever lands on
# a quantity slot. Party sales report -> only the sales side exists; reconcile is
# qty & amount vs the printed per-product subtotals (Amount col 3 == sum of the
# customer Amount values above it, exactly, e.g. 555.94+277.97 = 833.91).
# ---------------------------------------------------------------------------

_MONEY = r"-?\d[\d,]*\.\d+"

# value line: <name/optional> Quantity Rate Amount Amount  (exactly 4 numbers)
_VALUE = re.compile(
    rf"^(?P<name>.*?)\s*"
    rf"(?P<qty>{_MONEY})\s+"
    rf"(?P<rate>{_MONEY})\s+"
    rf"(?P<amount>{_MONEY})\s+"
    rf"(?P<total>{_MONEY})\s*$"
)

# trailing pack marker right before the numbers (e.g. "10/1", "20/2")
_PACK = re.compile(r"\s+\d+/\d+$")

# repeating page furniture / metadata (whitespace-collapsed, lowercased)
_SKIP = re.compile(
    r"^(new shakti distributor|kunwar singh colony|b\.s\. city|"
    r"item-wise customer-wise offtake|accounting period\b|"
    r"\d{2}/\d{2}/\d{4}\s+to\s+\d{2}/\d{2}/\d{4}$|mfg/mkt company|"
    r"item description\b|bonus quantity rate amount amount$|"
    r"total figures\b)",
    re.I,
)

# COMPANY band: a KLM-<div> heading (e.g. "KLM-COSMO", "KLM -DERMA",
# "KLM-COSMOCOR", "KLM-COSMOQ-LTD"). Whole line, all upper, starts with KLM.
_COMPANY = re.compile(r"^KLM\b[-\s A-Z0-9]*$")


def parse_r15_klm_customerwise_offtake(text):
    headers = ["Party Name", "Division", "Product Name", "Qty", "Rate", "Amount"]
    rows = []
    company = ""
    product = ""

    for raw in text.split("\n"):
        s = raw.strip()
        if not s:
            continue
        if _SKIP.match(s):
            continue

        m = _VALUE.match(s)
        if m:
            name = m.group("name").strip()
            if not name:
                # product subtotal line (numbers only) -> skip
                continue
            name = _PACK.sub("", name).strip()
            if not product:
                continue
            qty = m.group("qty").replace(",", "")
            rate = m.group("rate").replace(",", "")
            amount = m.group("amount").replace(",", "")
            rows.append([name, company, product, qty, rate, amount])
            continue

        # non-value line: either a COMPANY band or a PRODUCT band
        if _COMPANY.match(s):
            company = s
            continue

        # otherwise it is a PRODUCT band (must contain a letter)
        if re.search(r"[A-Za-z]", s):
            product = s

    return headers, rows
