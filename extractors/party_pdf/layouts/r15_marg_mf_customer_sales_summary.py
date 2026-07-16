import re

# ---------------------------------------------------------------------------
# Marg "Sales Detail Summary (Mf-Customer-Itemwise)" — item-code-bearing,
# DATELESS, Sale/Pur/MRP-amount variant (SOURABH MEDICOSE, Mandsaur; KLM
# distributor).
# Source file: SOURABH MEDICOSE/Party report/KLM PARTY.PDF
#
# Exact column header (gate token, whitespace-stripped + lowercased):
#     Item Name Item Code Qty Sale Amount Pur Amt Sch Qty MRP Amt
#     -> itemnameitemcodeqtysaleamountpuramtschqtymrpamt
#
# This is NOT the marg_register / klm_sales_detail_register siblings (those carry
# a leading SrNo + dd-mm-yyyy invoice date on every item row). Here item rows are
# DATELESS and start with the item name; they carry an explicit Item Code column
# and five trailing value columns: Qty, Sale Amount, Pur Amt, Sch Qty, MRP Amt.
# It also differs from r15_maruti_klm_batchwise_mf_customer (header
# "Item Batch Qty S. Qty S. Rate MRP Amount"): no Batch, no S.Rate, and it has an
# Item Code column plus a Pur Amt column. Because the generic report title
# "Sales Detail Summary (Mf-Customer-Itemwise)" makes it route to marg_summary,
# whose row regexes 0-row it (RED), it needs its own gated parser.
#
# Furniture (repeats per page):
#     SOURABH MEDICOSE                                          <- vendor banner
#     5, ARYA SAMAJ COMPLEX,... MANDSAUR-458001 Ph:...          <- address
#     Sales Detail Summary (Mf-Customer-Itemwise) From date...  <- report title
#     Item Name Item Code Qty Sale Amount Pur Amt Sch Qty MRP Amt  <- col header
#     Report Date : 02-Jul-26 14:51:32 / Page 1 of 9            <- footer
#
# Body nesting (three levels):
#     KLM COSMO-000435                             <- MF/division band  (skip)
#     1 WALK IN CUSTOMER, MANDSAUR CRETID          <- customer band (name, area)
#     EKRAN AQUA GEL 50GM 004748 2 602.35 550.38 0 0.00        <- item row
#     2 602.35 550.38 0 0.00                       <- customer subtotal  (skip)
#     66 23660.79 21859.79 9 5577.45               <- MF subtotal        (skip)
#     680 106621.40 98243.12 38 10230.50           <- grand total        (skip)
#
# Item-row grammar (five trailing numeric tokens peeled from the RIGHT):
#     <Item Name...> <ItemCode> <Qty> <Sale Amt> <Pur Amt> <Sch Qty> <MRP Amt>
#   * Qty and Sch Qty are integers; Sale Amt / Pur Amt / MRP Amt are decimals.
#   * The Item Code is the last text token before the five numbers; it is
#     alphanumeric and always contains a digit (e.g. 004748, PM0501, 006147).
#
# Field map (SACRED — qty and value never mixed):
#     Customer band  -> party_name / area (name before last comma; area after,
#                       leading "<n> " customer code stripped)
#     Item Name      -> product_name
#     Item Code      -> item_code (header maps to hsn_code slot)
#     Qty            -> qty        (sales_qty)         [integer col]
#     Sale Amount    -> amount     (verbatim; NEVER derived)
#     Pur Amt        -> purchase amount
#     Sch Qty        -> free_qty   (sales scheme/free qty) [integer col]
#     MRP Amt        -> mrp amount
# Sales-only party register; reconcile is column sums vs the printed grand total
# "680 106621.40 98243.12 38 10230.50" — matches to the paise on the ref file
# (qty 680, sale 106621.40, pur 98243.12, sch 38, mrp 10230.50).
# ---------------------------------------------------------------------------

# One numeric token: optional sign, digits, optional decimal.
_NUM = r"-?\d+(?:\.\d+)?"

# Item row: <text...> <ItemCode> Qty SaleAmt PurAmt SchQty MRPAmt.
_ITEM = re.compile(
    r"^(.*?\S)\s+"
    r"(" + _NUM + r")\s+(" + _NUM + r")\s+(" + _NUM + r")\s+"
    r"(" + _NUM + r")\s+(" + _NUM + r")\s*$"
)

# Bare value line (customer subtotal / MF total / grand total): exactly 5 numbers.
_ONLY5 = re.compile(r"^(?:" + _NUM + r"\s+){4}" + _NUM + r"\s*$")

# An item code: alphanumeric and contains at least one digit.
_CODE = re.compile(r"^[A-Za-z0-9]+$")

_FURN_PREFIX = (
    "sourabh medicose",
    "sales detail summary",
    "item name item code",
    "report date",
    "page ",
)


def _split_customer(raw):
    """'AAROGYA MEDICAL STORE MANDSAUR(M.P), MANDSAUR(M.P)' ->
    ('AAROGYA MEDICAL STORE MANDSAUR(M.P)', 'MANDSAUR(M.P)').

    Name is the text before the LAST comma; area is the remainder after it. A
    leading numeric customer code ('1 WALK IN CUSTOMER, ...') is stripped first.
    """
    s = raw.strip()
    s = re.sub(r"^\d+\s+", "", s)  # drop leading customer code
    if "," in s:
        head, _, tail = s.rpartition(",")
        name = head.strip().rstrip(",")
        area = tail.strip().strip(".")
        if not re.search(r"[A-Za-z]", area):
            area = ""
        return name, area
    return s, ""


def parse_r15_marg_mf_customer_sales_summary(text):
    H = [
        "Party Name",
        "Area",
        "Product Name",
        "Item Code",
        "Qty",
        "Sale Amount",
        "Pur Amt",
        "Sch Qty",
        "MRP Amt",
    ]
    rows = []
    party = area = ""

    for raw in text.split("\n"):
        s = re.sub(r"\s+", " ", raw.strip())
        if not s:
            continue

        low = s.lower()
        if any(low.startswith(p) for p in _FURN_PREFIX):
            continue
        # Marg address line: "5, ARYA SAMAJ ... Ph:..."
        if low.startswith("5, arya") or "ph:9479434599" in low:
            continue

        # Bare value lines (subtotals / totals) — skip.
        if _ONLY5.match(s):
            continue

        # Item row: five trailing numbers with a valid item-code prefix.
        m = _ITEM.match(s)
        if m:
            prefix = m.group(1).strip()
            toks = prefix.split()
            code = toks[-1] if toks else ""
            if (
                len(toks) >= 2
                and _CODE.match(code)
                and re.search(r"\d", code)
            ):
                item_name = " ".join(toks[:-1]).strip()
                if item_name and party:
                    rows.append([
                        party,
                        area,
                        item_name,
                        code,
                        m.group(2),  # Qty
                        m.group(3),  # Sale Amount
                        m.group(4),  # Pur Amt
                        m.group(5),  # Sch Qty
                        m.group(6),  # MRP Amt
                    ])
                continue

        # Manufacturer / division band: "KLM COSMO-000435", "KLM DERMACOR",
        # "KLM PHARMA-000413" — resets nothing structurally, just context.
        if re.match(r"^KLM\b", s) and "," not in s:
            party = area = ""
            continue

        # Otherwise, a line with a comma + letters is a customer band.
        if "," in s and re.search(r"[A-Za-z]", s):
            party, area = _split_customer(s)
            continue

    return H, rows
