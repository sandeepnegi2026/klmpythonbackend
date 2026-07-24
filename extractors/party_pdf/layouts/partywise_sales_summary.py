import re

# Marg "Partywise Sales Summary" (KAKADE AGENCIES / KLM — MVGold Wholesale HTML->PDF
# print export). One block per party: a PARTY header line carrying that block's running
# totals, followed by its PRODUCT lines. Every data line (party header and product alike)
# ends in the SAME six trailing numbers:
#
#     Particulars                 Qty  Sch Qty  Sch Amt  ID Amt  Amount   Amount - ID
#     A 1 MEDICAL RATNAGIRI       4    0        0.00     0.00     632.15   632.15    <- PARTY
#       KENZ LOTION 60ML          1    0        0.00     0.00     192.86   192.86    <- product
#       RESOTEN 10 10 TAB         3    0        0.00     0.00     439.29   439.29    <- product
#
# Party-vs-product discriminator: the party header's Qty and Amount are the running
# TOTAL of the product lines that follow it (up to the next party). We therefore walk
# forward accumulating product Qty/Amount and treat a line as the party header the moment
# the accumulated (qty, amount) of the block that follows it exactly equals the header's
# own (qty, amount). This dual constraint (qty AND amount) is self-reconciling and needs
# no name heuristics; on the reference file it splits 164 parties / 439 products with zero
# ambiguity and the product-amount total equals the printed grand total to the paise.

# name  Qty  SchQty  SchAmt  IDAmt  Amount  Amount-ID   (Qty/SchQty integer, 4 money x.xx)
_ROW = re.compile(
    r"^(?P<name>.*?\S)\s+"
    r"(?P<qty>\d+)\s+"
    r"(?P<schq>\d+)\s+"
    r"\d+\.\d{2}\s+"          # Sch Amt  (unused; always 0.00 here)
    r"\d+\.\d{2}\s+"          # ID Amt   (unused; always 0.00 here)
    r"(?P<amt>\d+\.\d{2})\s+"
    r"\d+\.\d{2}\s*$"         # Amount - ID (mirror of Amount)
)

# Repeating page furniture / heading / footer / grand-total lines (none carry the leading
# name + all six columns, but skip them explicitly to keep the data stream clean).
_SKIP = re.compile(
    r"^(particulars\b|company\s*:|partwise|partywise\s+sales\s+summary|"
    r"file:///|\d{1,2}/\d{1,2}/\d{2,4}\b|\d{2}/\d{2}/\d{4}\s+to\s+)",
    re.I,
)

_AMT_TOL = 0.05


def parse_partywise_sales_summary(text):
    """Marg 'Partywise Sales Summary' (KAKADE / KLM): party-header running totals over
    per-party product lines. Emits one row per PRODUCT line."""
    headers = ["Party Name", "Product Name", "Qty", "Free", "Amount"]

    data = []
    for raw in text.split("\n"):
        s = raw.strip()
        if not s or _SKIP.match(s):
            continue
        m = _ROW.match(s)
        if not m:
            continue
        data.append(
            {
                "name": m.group("name").strip(),
                "qty": int(m.group("qty")),
                "free": int(m.group("schq")),
                "amt": float(m.group("amt")),
            }
        )

    rows = []
    i, n = 0, len(data)
    while i < n:
        head = data[i]
        j = i + 1
        acc_qty = 0
        acc_amt = 0.0
        block = []
        matched = False
        while j < n:
            acc_qty += data[j]["qty"]
            acc_amt += data[j]["amt"]
            block.append(data[j])
            if acc_qty == head["qty"] and abs(acc_amt - head["amt"]) < _AMT_TOL:
                matched = True
                j += 1
                break
            # Overshot the header's amount -> this line already belongs to the next
            # party's block; stop and let head be reconsidered as a product below.
            if acc_amt > head["amt"] + _AMT_TOL:
                break
            j += 1

        if matched:
            for pr in block:
                rows.append(
                    [head["name"], pr["name"], str(pr["qty"]), str(pr["free"]),
                     f"{pr['amt']:.2f}"]
                )
            i = j
        else:
            # No clean block closed on this line — it is itself a stray product/echo
            # (e.g. the free-only 0/0 scheme line). Skip it and advance so a genuine
            # party header downstream still anchors correctly.
            i += 1

    return headers, rows
