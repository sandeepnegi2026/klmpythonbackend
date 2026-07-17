"""MEDICHEM PHARMA (Haridwar) 'Stock and Sales Statement from <d> to <d>' — KLM ERP.

One file per KLM division (COSMO / COSMOCOR / DERMA / DERMACOR / PHARMA). Flat,
right-aligned text export with EXPLICIT dashes for every zero cell, so each product
row carries a fixed run of exactly FOURTEEN trailing numeric tokens (with '-' -> 0).

HEADER (two physical lines, sales columns printed BEFORE purchase columns):
    Item Description  Opening  Sales  Sale  Sales   Sales   Purchase Purchase Purchase Purchase Other Closing Closing Expiry Expiry
                      Balance  Qty.   Free  Amount  Return  Qty.     Free     Amount   Return         Balance Amount  In     Out

14-token tail -> canonical map (index in the popped tail):
    [ 0] Opening Balance   -> opening_stock
    [ 1] Sales Qty.        -> sales_qty
    [ 2] Sale Free         -> sales_free
    [ 3] Sales Amount      -> sales_value        (can be negative, e.g. -462.53)
    [ 4] Sales Return      -> sales_return
    [ 5] Purchase Qty.     -> purchase_stock
    [ 6] Purchase Free     -> purchase_free
    [ 7] Purchase Amount   -> purchase_value
    [ 8] Purchase Return   -> purchase_return
    [ 9] Other             -> raw_other          (always blank in samples; kept raw)
    [10] Closing Balance   -> closing_stock      (can be negative)
    [11] Closing Amount    -> closing_stock_value
    [12] Expiry In         -> raw_expiry_in       (dropped from canonical)
    [13] Expiry Out        -> raw_expiry_out      (dropped from canonical)

RECONCILE (source balances EXACTLY):
    closing = opening + purchase + purchase_free + sales_return
              - sales - sales_free - purchase_return
    e.g. KLM COSMO TOTAL: 50 + 102 + 0 + 0 - 80 - 2 - 0 = 70  (printed closing 70)

We skip:
  * the report / company banner and the '='/'-' rule lines,
  * the two column-header lines,
  * the 'TOTAL' footer,
  * everything from the 'PENDING DEBIT NOTES' banner onward (a supplier ledger that
    also carries trailing numbers but is NOT stock movement).

The text layer is clean and flat (right-aligned cells never collapse — zero cells
print explicit '-'), so a straight token parse that pops the trailing 14 numbers is
robust and NO positional x-binning is required.
"""
import re

# One numeric cell: integer or decimal, optional leading '-', thousands-safe.
_NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*$")
_HEADER_RE = re.compile(r"^(item\s+description|balance\s+qty|opening\s+sales)", re.I)
_FOOTER_RE = re.compile(r"^(total|grand\s+total)\b", re.I)


def _is_cell(tok):
    """True for a numeric cell token OR a bare dash (blank/zero cell)."""
    if tok == "-":
        return True
    t = tok.replace(",", "")
    return bool(_NUM_RE.fullmatch(t)) and any(c.isdigit() for c in t)


def _to_f(tok):
    if tok == "-":
        return 0.0
    try:
        return float(tok.replace(",", ""))
    except ValueError:
        return 0.0


def parse_medichem_ss_expiry(text, file_bytes=None):
    records = []
    for raw in (text or "").splitlines():
        s = raw.strip()
        if not s:
            continue

        low = s.lower()
        # Stop entirely once the supplier debit-note ledger begins.
        if low.startswith("pending debit notes"):
            break

        # Skip rule lines (===... / ---...) and banner/header/footer lines.
        if set(s) <= {"=", "-"}:
            continue
        if _HEADER_RE.match(s) or _FOOTER_RE.match(low):
            continue

        toks = s.split()
        if len(toks) < 15:  # need item text + 14 cells
            continue

        # Pop exactly the 14 trailing cells (numbers or blank '-').
        tail = []
        body = list(toks)
        while body and _is_cell(body[-1]) and len(tail) < 14:
            tail.insert(0, body.pop())

        if len(tail) != 14 or not body:
            continue

        name = " ".join(body).strip()
        if not name:
            continue
        # A stray banner ending in 14 dash/number tokens would be caught above;
        # require at least one alphabetic char in the product name.
        if not any(c.isalpha() for c in name):
            continue

        v = [_to_f(t) for t in tail]
        records.append({
            "product_name": name,
            "opening_stock": v[0],
            "sales_qty": v[1],
            "sales_free": v[2],
            "sales_value": v[3],
            "sales_return": v[4],
            "purchase_stock": v[5],
            "purchase_free": v[6],
            "purchase_value": v[7],
            "purchase_return": v[8],
            "raw_other": v[9],
            "closing_stock": v[10],
            "closing_stock_value": v[11],
            "raw_expiry_in": tail[12],
            "raw_expiry_out": tail[13],
        })
    return records
