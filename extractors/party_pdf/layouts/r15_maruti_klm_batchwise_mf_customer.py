import re

# ---------------------------------------------------------------------------
# Marg "Sales Detail Register (Mf-Customer-Itemwise)" — item-first, DATELESS,
# MRP-bearing batchwise variant (MARUTI MEDICAL AGENCY, Ahmedabad; KLM LAB
# distributor).
# Source file: MARUTI MEDICAL AGENCY/Party report/KLM BATCHWISE 05-26.pdf
#
# Exact column header (gate token, whitespace-stripped + lowercased):
#     Item Batch Qty S. Qty S. Rate MRP Amount
#     -> itembatchqtys.qtys.ratemrpamount
#
# This is NOT the klm_sales_detail_register / marg_register sibling: those have
# a leading "SrNo Date" (invoice serial + dd-mm-yyyy date) on every item row and
# NO MRP column. Here the item rows carry NO date and NO invoice number, they
# start with the Item name (or a bare Batch, or bare numbers on repeat lines) and
# they carry an MRP column between Sale Rate and Amount. Because it still contains
# the generic title "Sales Detail Register ... Mf-Customer..." it otherwise routes
# to marg_register, whose date-anchored row regexes 0-row it (RED).
#
# Furniture (single page here, repeats per page):
#     MARUTI MEDICAL AGENCY.                                   <- vendor banner
#     SHOP NO:3, ... AHMEDABAD-382350 Ph:7777923922            <- address
#     Sales Detail Register (Mf-Customer-Itemwise) From date.. <- report title
#     Item Batch Qty S. Qty S. Rate MRP Amount                 <- column header
#
# Body nesting (three levels):
#     MF : M00062 - KLM LAB COSMO [ COSMO ]        <- MF/division band  (skip)
#     1. Invoice 20 4 5080.23                      <- invoice roll-up   (skip)
#     PUSHPAM DRUG HOUSE, AHMEDABAD - 3732.08      <- PARTY band  (name, area)
#     EKRAN AQUA GEL 50GM AA3601 10. 2. 277.97 410.00 2696.31  <- item row
#     KOJITIN EMULGEL 15GM CB504 5. 1. 213.56 315.00 1035.77   <- item row
#     270. 54. 5080.23                             <- MF subtotal roll-up (skip)
#
# Item-row grammar (numeric columns peeled POSITIONALLY from the RIGHT, because
# Batch may be all-uppercase-alnum and Item names contain spaces & pack sizes):
#     <Item?> <Batch?> <Qty>. [<S.Qty>.] <S.Rate> <MRP> <Amount>
#   * Last THREE tokens are proper decimals = S.Rate, MRP, Amount.
#   * The trailing-dot integers immediately left of them = Qty (+ optional S.Qty
#     free column). At least one (Qty) is required.
#   * The remaining left tokens are Item Name + optional Batch; a trailing token
#     matching ^[A-Z]{1,3}\d[A-Z0-9]* is the Batch (e.g. AA3601, CB504, BC565).
#   * Continuation rows repeat the same item (bare Batch => carry item; bare
#     numbers => carry item + batch), so the last seen item/batch are carried.
#
# Field map (SACRED — qty and value never mixed):
#     PARTY band            -> party_name / area (name before 1st comma; area is
#                              the remainder with trailing "- <amount>" stripped)
#     Item text             -> product_name
#     Batch                 -> batch
#     Qty (trailing-dot)    -> qty        (sales_qty)
#     S.Qty (trailing-dot)  -> free       (sales_free)
#     S.Rate                -> rate
#     MRP                   -> mrp
#     Amount                -> amount     (verbatim; NEVER derived from qty*rate)
# Only the sales side exists (party sales register); reconcile is amount vs the
# printed per-party "- <amount>" subtotals, which match to the paise on the
# reference file.
# ---------------------------------------------------------------------------

# A proper decimal (S.Rate / MRP / Amount), possibly comma-grouped / negative.
_DEC = re.compile(r"^-?[\d,]+\.\d+$")
# A trailing-dot integer (Qty / S.Qty), possibly negative: "10.", "0.".
_INTDOT = re.compile(r"^-?\d+\.$")
# A batch token: 1-3 leading letters then a digit then alnum (AA3601, CB504, BJ601).
_BATCH = re.compile(r"^[A-Z]{1,3}\d[A-Z0-9]*$")

_SKIP_PREFIX = (
    "MF :",
    "MF:",
    "Sales Detail",
    "Item Batch",
    "Report Date",
    "Amount =",
    "Page ",
    "Ph:",
)


def _split_party(raw):
    """'PUSHPAM DRUG HOUSE, AHMEDABAD - 3732.08' -> ('PUSHPAM DRUG HOUSE',
    'AHMEDABAD'). Name is text before the first comma; area is the remainder with
    the trailing '- <amount>' subtotal stripped."""
    # Drop a trailing " - <number>" (the per-party amount roll-up).
    s = re.sub(r"\s*-\s*[\d,]+\.?\d*\s*$", "", raw.strip())
    parts = [p.strip() for p in s.split(",")]
    name = parts[0].strip()
    area = ", ".join(parts[1:]).strip() if len(parts) > 1 else ""
    area = re.sub(r"\s+", " ", area).strip(" -.")
    if not re.search(r"[A-Za-z]", area):
        area = ""
    return name, area


def _parse_item(s):
    """Peel an item row -> (item, batch, qty, free, rate, mrp, amount) or None.

    None when the line does not end in the S.Rate/MRP/Amount three-decimal run,
    which excludes MF bands, invoice roll-ups, party bands and subtotal lines."""
    toks = s.split()
    if len(toks) < 4:
        return None
    if not (_DEC.match(toks[-1]) and _DEC.match(toks[-2]) and _DEC.match(toks[-3])):
        return None
    amount, mrp, rate = toks[-1], toks[-2], toks[-3]
    i = len(toks) - 3
    qcols = []
    while i - 1 >= 0 and _INTDOT.match(toks[i - 1]):
        qcols.insert(0, toks[i - 1].rstrip("."))
        i -= 1
    if not qcols:
        return None
    qty = qcols[0]
    free = qcols[1] if len(qcols) >= 2 else ""
    prefix = toks[:i]  # item name + optional batch
    batch = ""
    if prefix and _BATCH.match(prefix[-1]):
        batch = prefix[-1]
        item = " ".join(prefix[:-1]).strip()
    else:
        item = " ".join(prefix).strip()
    return item, batch, qty, free, rate, mrp, amount


def parse_r15_maruti_klm_batchwise_mf_customer(text):
    H = [
        "Party Name",
        "Area",
        "Product Name",
        "Batch",
        "Qty",
        "Free",
        "Rate",
        "MRP",
        "Amount",
    ]
    rows = []
    party = area = ""
    last_item = last_batch = ""
    for raw in text.split("\n"):
        s = re.sub(r"\s+", " ", raw.strip())
        if not s:
            continue
        if any(s.startswith(p) for p in _SKIP_PREFIX):
            continue

        parsed = _parse_item(s)
        if parsed:
            item, batch, qty, free, rate, mrp, amount = parsed
            if item:
                last_item = item
                last_batch = batch  # a new item resets the carried batch
            elif batch:
                last_batch = batch  # bare batch: same item, new batch
            item = item or last_item
            batch = batch or last_batch
            if not item or not party:
                continue
            rows.append(
                [party, area, item, batch, qty, free, rate, mrp, amount]
            )
            continue

        # invoice roll-up "1. Invoice 20 4 5080.23" and bare subtotal roll-ups
        # "270. 54. 5080.23" start with a digit -> not a party band.
        if re.match(r"^\d", s):
            continue

        # A party band carries a comma + letters and ends with "- <amount>".
        if "," in s and re.search(r"[A-Za-z]", s):
            party, area = _split_party(s)
            last_item = last_batch = ""

    return H, rows
