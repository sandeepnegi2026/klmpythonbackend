"""DEEPA(A) AGENCIES 'STOCK AND SALES STATEMENT' — dot-matrix KLM export.

Header (two physical lines, RECEIPT is split "REC-" / "EIPT"):
    PRODUCT NAME  OPEN  REC-  ADJ  ADJ  TOTAL  SALES  CLOSE  ORD.QTY  EXCES  APR  MAR
                  STOCK EIPT  (-)  (+)  STOCK  QTY    STOCK  ( 1.00)  VALUE  SALES SALES

Each printed page carries ONE division band ("___SUP:YOGIRAM PHARMA MFR:I1 KLM -
(DERMA)__") and is followed by junk sections that must NOT become rows:
"_SHORT EXPIRY PRODUCTS_", "_LONG PENDING CLAIMS AS ON 30/05/26_", per-band rupee
footers ("Cl.Stk Value Ex.Stk.Value ..."), and "PERUM---" decoration.  The full
banner "STOCK AND SALES STATEMENT FOR THE MONTH" reprints at the top of every band,
so we use it to reset the section state machine back into the data block.

Data rows carry 10 or 11 trailing numbers plus an optional mid-row '#' flag:
    "CANROLFIN CREAM. 15GM 4 0 0 0 # 4 1 3 -2 307 0 2"  (11 nums + '#')
    "HBSALIC OINT. 20GM 52 0 0 0 52 29 23 6 24 47"      (10 nums, EXCES blank)

Column order (after dropping '#'):
    OPEN STOCK, RECEIPT, ADJ(-), ADJ(+), TOTAL STOCK, SALES QTY, CLOSE STOCK,
    ORD.QTY, [EXCES VALUE — rupees, only when ORD.QTY<0], APR SALES, MAR SALES.

We FRONT-anchor the first 8 values of the trailing numeric run and IGNORE v8+:
    opening_stock  <- v0  OPEN STOCK
    purchase_stock <- v1  RECEIPT
    purchase_return<- v2  ADJ(-)   (vendor SUBTRACTS)
    sales_return   <- v3  ADJ(+)   (vendor ADDS — same sign as the triage equation)
    total_stock    <- v4  TOTAL STOCK
    sales_qty      <- v5  SALES QTY
    closing_stock  <- v6  CLOSE STOCK
    order_qty      <- v7  ORD.QTY
EXCES VALUE (rupees) and APR/MAR SALES (prior-month info) are dropped — they must
never land in a qty field.

RECONCILE (canonical): closing == opening + purchase + sales_return - purchase_return
- sales; and the internal cross-check TOTAL == OPEN + RECEIPT - ADJ(-) + ADJ(+).
Both hold 175/175 on MAY STATMENT DEEPAA.pdf.
"""
import re

from extractors.stock_pdf.parse_common import _split_product_pack

# The full report banner reprints at the top of every division band — we use it to
# reset the state machine back into the data block after a junk section.
_BANNER = "stock and sales statement for the month"

# Junk sections that follow each band; once entered we skip until the next banner.
_SKIP_MARKERS = ("short expiry products", "long pending claims")

# Division: "___SUP:YOGIRAM PHARMA MFR:I1 KLM - (DERMA)__" -> DERMA
_DIV_RE = re.compile(r"MFR:\S+\s+KLM\s*-\s*\(([^)]+)\)")

# A single numeric cell: signed integer or decimal, thousands-safe.
_NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*$")


def _is_num(tok):
    t = tok.replace(",", "")
    return bool(_NUM_RE.fullmatch(t)) and any(c.isdigit() for c in t)


def _to_f(tok):
    try:
        return float(tok.replace(",", ""))
    except ValueError:
        return 0.0


def parse_stock_open_rec_adj_close(text):
    records = []
    division = ""
    skip = False

    for raw in (text or "").splitlines():
        s = raw.strip()
        if not s:
            continue
        low = s.lower()

        # The banner reprints atop every band -> re-enter the data block.
        if _BANNER in low:
            skip = False
            continue

        # Junk sections (short-expiry / long-pending claims) -> skip until banner.
        if any(m in low for m in _SKIP_MARKERS):
            skip = True
            continue

        # Division band line — always update, even mid-skip (the SUP: line for the
        # NEXT band prints after the banner reset, so this only fires in-block).
        m = _DIV_RE.search(s)
        if m:
            division = m.group(1).strip()
            continue

        if skip:
            continue

        # Skip rule/decoration lines (====, ----, PERUM----) and the column header.
        if s.startswith("=") or s.startswith("-") or s.startswith("_"):
            continue
        compact = low.replace(" ", "")
        if "productname" in compact or "openrec-adj" in compact:
            continue

        # Drop mid-row '#' flag tokens, then pop the trailing numeric run.
        toks = [t for t in s.split() if t != "#"]
        if len(toks) < 11:  # >=10 numbers + >=1 product-text token
            continue

        tail = []
        body = list(toks)
        while body and _is_num(body[-1]):
            tail.insert(0, body.pop())

        # Data rows carry >=10 trailing numbers; the remaining body must be product
        # text (contains a letter).  This alone excludes claims rows ('15573_' breaks
        # the run), SHORT-EXPIRY rows ('09-26' breaks it), 'TOTAL Rs. 26471 20444'
        # (len 2), and the rupee band footers.
        if len(tail) < 10 or not body:
            continue
        name = " ".join(body).strip()
        if not re.search(r"[A-Za-z]", name):
            continue

        vals = [_to_f(t) for t in tail]
        # FRONT-anchor the first 8; ignore v8+ (EXCES VALUE / APR / MAR SALES).
        v = vals[:8]

        prod, pack = _split_product_pack(name)
        prod = re.sub(r"\s+", " ", prod).strip()
        if not prod or len(prod) < 3:
            continue

        rec = {
            "product_name": prod,
            "pack": pack,
            "division": division,
            "opening_stock": v[0],
            "purchase_stock": v[1],
            "purchase_return": v[2],   # ADJ(-)  vendor subtracts
            "sales_return": v[3],      # ADJ(+)  vendor adds
            "total_stock": v[4],
            "sales_qty": v[5],
            "closing_stock": v[6],
            "order_qty": v[7],
        }
        if pack and prod != name:
            # The split moved a trailing size token out of the name; keep the full
            # string so enrichment can first try an exact catalog hit on it
            # (see core/product_master).
            rec["_prestrip_name"] = name
        records.append(rec)

    return records
