"""Medicine Traders (Ajmer) 'Sales & Stock Statement' — SwilERP retail export.

Header (two physical lines):
    PRODUCT NAME  PACKING  Op.Bal.  Receipt  Free Q  Total  Issue  Free Q  Closing
    (units row)   Qty.     Qty.     Qty      Qty.    Qty.    Qty    Balance

Each data line is:  <product name + pack text>  then exactly SEVEN trailing numbers:
    [0] Op.Bal   [1] Receipt   [2] Receipt-Free   [3] Total   [4] Issue
    [5] Issue-Free   [6] Closing(Balance)

MAPPING
    opening_stock  <- Op.Bal   (vals[0])
    purchase_stock <- Receipt  (vals[1])
    purchase_free  <- Recv-Free (vals[2])
    sales_qty      <- Issue    (vals[4])
    sales_free     <- Issue-Free (vals[5])
    closing_stock  <- Closing  (vals[6])
    (Total = vals[3] is a printed cross-check = Op.Bal+Receipt+Recv-Free; ignored.)

RECONCILE (canonical, purchase_return = sales_return = 0):
    closing = opening + purchase + purchase_free - sales - sales_free
    e.g. GA 12 CREAM: 109 + 50 + 0 - 56 - 10 = 93  (EXACT)
Half-unit frees (e.g. 1.50) are genuine and reconcile exactly.

The text layer is clean and flat (right-aligned cells never blank out — zero-movement
rows print explicit 0s), so a straight token parse that pops the trailing 7 numbers is
robust; no positional x-binning is required. We skip the report/company banner, the
column-header pair, the per-division band lines ("KLM PHARMA", "KLM COSMO CORE", ...),
and the TOTAL / GRAND TOTAL footer lines (which carry 7 rupee-scale numbers but no
product text of their own).
"""
import re

# A single numeric cell: integer or decimal (half-unit frees like 1.50), thousands-safe.
_NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*$")

# Division bands ("KLM PHARMA", "KLM PAEDITRIC", "KLM COSMO CORE", ...) and the two
# header lines carry no trailing 7-number cluster; the footer TOTAL rows do, so those
# are gated by a label test below.
_FOOTER_RE = re.compile(r"^(grand\s+total|total)\b", re.I)
_HEADER_RE = re.compile(r"^(product\s+name|qty\.?\b|page\s+no\.)", re.I)


def _is_num(tok):
    t = tok.replace(",", "")
    return bool(_NUM_RE.fullmatch(t)) and any(c.isdigit() for c in t)


def _to_f(tok):
    try:
        return float(tok.replace(",", ""))
    except ValueError:
        return 0.0


def parse_medtraders_sales_stock_statement(text, file_bytes=None):
    records = []
    for raw in (text or "").splitlines():
        s = raw.strip()
        if not s:
            continue
        low = s.lower()
        if _HEADER_RE.match(s) or _FOOTER_RE.match(low):
            continue

        toks = s.split()
        if len(toks) < 8:
            continue

        # Pop exactly the 7 trailing numeric tokens.
        tail = []
        body = list(toks)
        while body and _is_num(body[-1]) and len(tail) < 7:
            tail.insert(0, body.pop())

        # Must have all 7 measure columns and some product text left over.
        if len(tail) != 7 or not body:
            continue

        # Division bands ("KLM COSMO CORE") have no numeric tail so they never reach
        # here; but guard against a lone banner that happens to end in digits.
        name = " ".join(body).strip()
        if not name:
            continue

        vals = [_to_f(t) for t in tail]
        opening, receipt, recv_free, _total, issue, issue_free, closing = vals

        records.append({
            "product_name": name,
            "opening_stock": opening,
            "purchase_stock": receipt,
            "purchase_free": recv_free,
            "sales_qty": issue,
            "sales_free": issue_free,
            "closing_stock": closing,
        })
    return records
