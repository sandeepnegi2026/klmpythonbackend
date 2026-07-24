import re

# ---------------------------------------------------------------------------
# KLM "Sales Detail Register (Mf-Customerwise)" — SrNo-first amount-bearing
# variant (AAGAM PHARMAKON, VISNAGAR MEDICAL STORE).
#
# Furniture (repeated every page):
#   "<STOCKIST NAME>" | "<address> Ph:..." |
#   "Sales Detail Register (Mf-Customerwise) From date DD-MM-YY to DD-MM-YY" |
#   column header "SrNo Date Item Name Batch No Qty Sch Qty Sch Disc Sale Rate
#   Amount".
#
# Body layout (three levels):
#   * DIVISION band  — "KLM - COSMOCOR DIVISION - M00114",
#     "KLM LAB. ( PEDIATRIC DIV.) - MF070", "KLM COSMO DIVISION - 82" (no party,
#     no item; skipped).
#   * PARTY band     — "<CUSTOMER NAME>, <AREA> <TOWN>" (has a comma + letters,
#     ends with letters not numbers). Carried down onto its item rows.
#   * ITEM row       — "<SrNo> <DD-MM-YYYY> <Item Name> <Batch> <Qty>. [<SchQty>.]
#     <Sale Rate> <Amount>".  SrNo is the invoice serial (SZ####), the date is
#     dd-mm-YYYY (four-digit year), Qty and Sch Qty carry a TRAILING DOT, while
#     Sale Rate and Amount are proper decimals. The Sch Disc column is present in
#     the header but never populated in the body.
#   * SUBTOTAL lines — bare numeric roll-ups "18. 3. 0.00 2374.04" (start with a
#     digit; skipped).
#
# The Amount column IS printed here, so Amount is taken verbatim (NEVER derived
# from qty x rate). This distinguishes the layout from the PRATHNA-UNITY sibling
# (prathna_register), whose Amount column is blank so its rows end with
# "<Qty>. <Rate>" (two numbers) and Amount must be computed. The sibling's
# $-anchored regex rejects these amount-bearing rows, so both are additive.
#
# Batch tokens can themselves be all-numeric (e.g. "937") or carry an internal
# space ("SBP 020"), so the numeric columns are peeled POSITIONALLY from the end
# of the row rather than by counting tokens: Amount and Sale Rate are the last
# two decimals, then the trailing-dot integers immediately before them are
# Qty (+ optional Sch Qty); everything to their left is Item Name + Batch.
# ---------------------------------------------------------------------------

H = [
    "Party Name",
    "Area",
    "Item Name",
    "Batch",
    "Date",
    "Qty",
    "Free Qty",
    "Sch Disc",
    "Rate",
    "Amount",
]

# SrNo (alnum serial) + dd-mm-YYYY date + rest.
_ROW = re.compile(r"^(\w[\w-]*)\s+(\d{2}-\d{2}-\d{4})\s+(.+)$")
# A trailing-dot integer (Qty / Sch Qty), possibly negative: "5.", "-1.".
_INTDOT = re.compile(r"^-?\d+\.$")
# A proper decimal (Sale Rate / Amount), possibly negative and comma-grouped.
_DEC = re.compile(r"^-?[\d,]+\.\d+$")


def _split_party(raw):
    """'ANANTA DERMATOLOGY AND COS. CLINIC, LUNAWA LUDNAWADA' -> (name, area).

    Name is the text before the first comma; area is the remainder with any
    trailing customer-code ('- 398', '.- 375') stripped. Mirrors the
    marg_register party split so the two layouts read the same shape."""
    parts = [p.strip() for p in raw.split(",")]
    name = parts[0].strip()
    area = ", ".join(parts[1:]).strip() if len(parts) > 1 else ""
    # Drop a trailing "- <code>" / ".- <code>" (customer code, e.g. "- 398").
    area = re.sub(r"[.\-\s]+\d{2,6}\s*$", "", area).strip(" .-")
    area = re.sub(r"\s+", " ", area)
    return name, area


def _parse_tail(rest):
    """Split the post-date remainder into (item_name, batch, qty, free, disc,
    rate, amount). Returns None if the row does not end with a Rate+Amount pair.

    Peels numeric columns off the RIGHT: last two tokens = Sale Rate, Amount
    (decimals); the trailing-dot integers just before them = Qty then optional
    Sch Qty / Sch Disc. The remaining left tokens are Item Name + Batch; the
    last of those is the Batch."""
    toks = rest.split()
    if len(toks) < 3:
        return None
    if not (_DEC.match(toks[-1]) and _DEC.match(toks[-2])):
        return None
    amount = toks[-1]
    rate = toks[-2]
    i = len(toks) - 2
    # Collect the trailing-dot integers directly left of the rate.
    qcols = []
    while i - 1 >= 0 and _INTDOT.match(toks[i - 1]):
        qcols.insert(0, toks[i - 1].rstrip("."))
        i -= 1
    if not qcols:
        return None
    qty = qcols[0]
    free = qcols[1] if len(qcols) >= 2 else ""
    disc = qcols[2] if len(qcols) >= 3 else ""
    prefix = toks[:i]  # item name + batch
    if len(prefix) < 2:
        return None
    batch = prefix[-1]
    item = " ".join(prefix[:-1]).strip()
    if not item:
        return None
    return item, batch, qty, free, disc, rate, amount


def _is_division(s):
    su = s.upper()
    if su.startswith("KLM "):
        return True
    # "... DIVISION - <code>" / "... DIV.) - <code>" group headers.
    if re.search(r"(DIVISION|DIV\.\))\s*-\s*\S+$", su):
        return True
    return False


def parse_klm_sales_detail_register(text):
    rows = []
    party = area = ""
    for raw in text.split("\n"):
        s = re.sub(r"\s+", " ", raw.strip())
        if not s:
            continue

        m = _ROW.match(s)
        if m:
            parsed = _parse_tail(m.group(3))
            if parsed and party:
                item, batch, qty, free, disc, rate, amount = parsed
                rows.append([
                    party,
                    area,
                    item,
                    batch,
                    m.group(2),
                    qty,
                    free,
                    disc,
                    rate,
                    amount,
                ])
            continue

        # Division / group header -> not a party.
        if _is_division(s):
            continue

        # Report chrome.
        su = s.upper()
        if (
            "SALES DETAIL" in su
            or su.startswith(("SRNO", "PAGE", "FROM "))
            or "PH:" in su
            or set(s) <= set("-")
        ):
            continue

        # Bare numeric subtotal roll-ups ("18. 3. 0.00 2374.04").
        if re.match(r"^-?[\d.]", s):
            continue

        # A customer heading (store name + ', <area>') sets the current party.
        if "," in s and re.search(r"[A-Za-z]", s):
            party, area = _split_party(s)

    return H, rows
