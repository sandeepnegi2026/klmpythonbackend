import re

# ---------------------------------------------------------------------------
# BHAGYODAY AGENCIES "Sales Detail Register (Mf-Areawise)" — the Mf-AREAWISE
# sibling of klm_sales_detail_register (Mf-Customerwise). Per-invoice SALES
# report banded MF -> Area -> Customer.
#
# Furniture:
#   "<STOCKIST>" | "<address> Ph:.." |
#   "Sales Detail Register (Mf-Areawise) From date DD-MM-YY to DD-MM-YY" |
#   header "InvNo. Date Item Batch Qty S. Rate MRP S. Qty Di% S. Disc. Amount".
#
# Bands:
#   * "MF. : MF0017 - KLM PHARMA DIVISION [ PHARMA ]"   (division; skipped)
#   * "Area : GHATLODIA 1. 0. 0.00 124.71"              (area + running totals)
#   * "Customer : PRAKASH HEALTHCARE, GHATLODIYA 1. 0. 0.00 124.71"
#        -> party = text before the comma; area = remainder minus the trailing
#           running-total block.
#
# Item row: "<InvNo> <DD-MM-YY> <Item> <Batch> <Qty>. <S.Rate> <MRP> <Di%>. <Amount>".
#   Date is TWO-digit-year (02-05-26) — this is the ONLY structural difference in
#   the row shape from the Mf-Customerwise variant, whose _ROW needs \d{4}.
#   The five trailing numbers are Qty(dot-int), S.Rate(dec), MRP(dec), Di%(dot-int),
#   Amount(dec). The S.Qty and S.Disc header columns are never populated.
#   Amount is printed (Amount = Q x R - Disc) and taken VERBATIM (never derived).
#   Some rows omit the Item+Batch (the ERP suppresses a repeated product), so an
#   item-less row carries the previous row's item/batch down.
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

# InvNo (alnum serial) + dd-mm-YY (2-digit year) + rest.
_ROW = re.compile(r"^(\w[\w-]*)\s+(\d{2}-\d{2}-\d{2})\s+(.+)$")
_INTDOT = re.compile(r"^-?\d+\.$")            # Qty / Di% : "1.", "3.", "-1."
_DEC = re.compile(r"^-?[\d,]+\.\d+$")          # S.Rate / MRP / Amount


def _split_party(raw):
    """'PRAKASH HEALTHCARE, GHATLODIYA' -> ('PRAKASH HEALTHCARE', 'GHATLODIYA').

    Strips any trailing running-total block ('1. 0. 0.00 124.71') the Customer
    band carries, then splits name (before comma) from area (after)."""
    # Drop the trailing running-total run: <int>. <int>. <dec> <dec>
    raw = re.sub(r"(?:\s-?\d+\.){1,3}(?:\s-?[\d,]+\.\d+){1,3}\s*$", "", raw).strip()
    parts = [p.strip() for p in raw.split(",")]
    name = parts[0].strip()
    area = ", ".join(parts[1:]).strip() if len(parts) > 1 else ""
    area = re.sub(r"\s+", " ", area)
    return name, area


def _parse_tail(rest):
    """Peel (item, batch, qty, rate, amount) off the RIGHT of the post-date text.

    Trailing five numbers = Qty(dot-int) S.Rate(dec) MRP(dec) Di%(dot-int)
    Amount(dec). Returns (item, batch, qty, rate, amount) or None if the shape
    does not match. item/batch are "" when the ERP suppressed a repeated product
    (caller carries the previous ones down)."""
    toks = rest.split()
    if len(toks) < 5:
        return None
    amount, di, mrp, rate, qty = toks[-1], toks[-2], toks[-3], toks[-4], toks[-5]
    if not (
        _DEC.match(amount)
        and _INTDOT.match(di)
        and _DEC.match(mrp)
        and _DEC.match(rate)
        and _INTDOT.match(qty)
    ):
        return None
    prefix = toks[:-5]  # item name + batch (may be empty)
    if prefix:
        batch = prefix[-1]
        item = " ".join(prefix[:-1]).strip()
        if not item:  # single leftover token = item with no separate batch
            item, batch = batch, ""
    else:
        item = batch = ""  # carried down by the caller
    return item, batch, qty.rstrip("."), rate, amount


def parse_r15_klm_sales_detail_areawise(text):
    rows = []
    party = area = ""
    prev_item = prev_batch = ""
    for raw in text.split("\n"):
        s = re.sub(r"\s+", " ", raw.strip())
        if not s:
            continue

        m = _ROW.match(s)
        if m:
            parsed = _parse_tail(m.group(3))
            if parsed and party:
                item, batch, qty, rate, amount = parsed
                if not item:              # suppressed repeat -> carry down
                    item, batch = prev_item, prev_batch
                else:
                    prev_item, prev_batch = item, batch
                if item:
                    rows.append([
                        party, area, item, batch, m.group(2),
                        qty, "", "", rate, amount,
                    ])
            continue

        low = s.lower()
        if low.startswith("customer :") or low.startswith("customer:"):
            party, area = _split_party(s.split(":", 1)[1].strip())
            continue
        if low.startswith("area :") or low.startswith("area:"):
            continue      # area comes from the Customer band's comma tail
        if low.startswith(("mf. :", "mf.:", "mf :", "mf:")):
            continue      # division band
        # Report chrome + bare numeric subtotals.
        su = s.upper()
        if (
            "SALES DETAIL" in su
            or su.startswith(("INVNO", "PAGE", "FROM ", "REPORT DATE", "AMOUNT ="))
            or "PH:" in su
            or re.match(r"^-?[\d.]", s)
            or set(s) <= set("-")
        ):
            continue

    return H, rows
