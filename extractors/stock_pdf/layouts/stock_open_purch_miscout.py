"""CHAMPAVATI PHARMA LLP (GAJANAN ENT., BEED) 'Stock and sales Statement' — KLM ERP.

Header (two physical lines, the ERP misspells 'Particular' as 'Purticular'):
    Purticular  Pkg.  Open.  Purch.  Sales  Sales  Misc.  Close  Closing  Sales
                      Qty.   Qty.    Ret.   & DC   Out    Stock  Value    Value

Ten printed columns.  The six leading numeric columns are QUANTITIES, the last two
are RUPEE VALUES.  Zero cells print '-'.  Each data line therefore ends in EXACTLY
eight trailing tokens (numeric or '-'):

    [0] Open.Qty   [1] Purch.Qty   [2] Sales Ret.   [3] Sales & DC
    [4] Misc.Out   [5] Close Stock  [6] Closing Value  [7] Sales Value

    e.g.  'EPISERT 30GMS 30GMS  22 12 - 15 - 19 4614.34 2431.60'
          'MELABOOST TAB 10S     7 60 - 28 1 38 6440.62 4576.23'   (Misc.Out=1)
          'HISTABIL TABS. 10S   50 -  -  - 50  - -       -'         (written off)

FIELD MAPPING (v0..v7):
    opening_stock       <- Open.Qty     (v0)
    purchase_stock      <- Purch.Qty    (v1)
    sales_return        <- Sales Ret.   (v2)   vendor ADDS it back
    sales_qty           <- Sales & DC   (v3)
    purchase_return     <- Misc. Out    (v4)   vendor SUBTRACTS it (write-off slot,
                                               same convention as klm_sale_stock_stmt's
                                               StkAdj -> purchase_return remap)
    closing_stock       <- Close Stock  (v5)
    closing_stock_value <- Closing Value(v6)   rupees
    sales_value         <- Sales Value  (v7)   rupees

RECONCILE (canonical):
    closing = opening + purchase + sales_return - purchase_return - sales
    e.g. EPISERT 30GMS: 22 + 12 + 0 - 0 - 15 = 19  (EXACT)
         MELABOOST TAB:  7 + 60 + 0 - 1 - 28 = 38  (EXACT)
Verified EXACT on 248/248 rows.  The two rupee columns sum to the printed per-band
footers and to the grand total 'Grand Total. 1762184.23 724961.36'.

DIVISION BANDS ('KLM COSMO CORE', 'KLM DERMA DIVISION', ...) are standalone lines
matching  ^KLM\\s+[A-Z][A-Z .]*$  with no digits — they are CAPTURED as the current
division (NOT skipped: parse_common._skip_line would drop a bare 'KLM <DIV>' line,
which is what we want captured here, so we detect division bands explicitly and do
NOT route product rows through _skip_line's KLM guard).

Things this parser must exclude:
  * the two-float per-band value footers ('199749.38 83005.06') — only a 2-token tail
  * the grand total line ('Grand Total. 1762184.23 724961.36') — only a 2-token tail
  * orphan product-name wrap lines ('30ML', 'GEL', 'WASH', ...) — no numeric tail
  * the whole expiry annex + page-7 overflow after the hard-stop marker
    'List of Items with expiry between'
"""
import re

from core.pack_match import extract_pack_from_product as _split_product_pack

# A single numeric cell: integer or decimal (thousands-safe), or a bare '-' (=> 0).
_NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*$")

# Division band: 'KLM COSMO CORE', 'KLM DERMA DIVISION', 'KLM GYNEC', 'KLM PAEDIA' ...
# Uppercase letters/spaces/dots only, no digit — a KLM-branded PRODUCT always carries
# a trailing numeric tail (and mixed case / a pack), so it never matches this.
_DIVISION_RE = re.compile(r"^KLM\s+[A-Z][A-Z .]*$")

# Page banner / header lines to skip outright (division bands handled separately).
_SKIP_PREFIXES = (
    "purticular",
    "qty.",
    "company :",
    "gstn",
    "stock and sales statement",
    "champavati pharma",
    "page :",
    "product pkg",          # expiry-annex header (defensive; after hard-stop anyway)
)

# Hard stop: everything from here on is the expiry annex + printer overflow.
_HARD_STOP = "list of items with expiry between"


def _is_cell(tok):
    """A numeric cell ('12', '4614.34', '1,234') or a bare '-' zero placeholder."""
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


def parse_stock_open_purch_miscout(text):
    records = []
    division = ""
    for raw in (text or "").splitlines():
        s = raw.strip()
        if not s:
            continue
        low = s.lower()

        # Hard stop at the expiry annex — nothing after it is a stock row.
        if _HARD_STOP in low:
            break

        # Division band -> set current division, emit nothing.
        if _DIVISION_RE.match(s):
            division = s.strip()
            continue

        if low.startswith(_SKIP_PREFIXES):
            continue

        toks = s.split()
        if len(toks) < 9:  # need >=1 body token + 8 tail cells
            continue

        # Pop up to EXACTLY 8 trailing numeric/'-' cells.
        tail = []
        body = list(toks)
        while body and _is_cell(body[-1]) and len(tail) < 8:
            tail.insert(0, body.pop())

        # Require the full 8-cell tail, a non-empty body, and a letter in the body
        # (excludes the 2-float band footers, the grand-total line, orphan wrap
        # lines, and expiry rows whose batch token breaks the numeric run).
        if len(tail) != 8 or not body:
            continue
        name = " ".join(body).strip()
        if not re.search(r"[A-Za-z]", name):
            continue

        vals = [_to_f(t) for t in tail]
        (opening, purchase, sales_return, sales_qty,
         misc_out, closing, closing_value, sales_value) = vals

        prod, pack = _split_product_pack(name)
        prod = re.sub(r"\s+", " ", prod).strip()
        if not prod:
            prod = name

        records.append({
            "product_name": prod,
            "pack": pack,
            "opening_stock": opening,
            "purchase_stock": purchase,
            "sales_return": sales_return,
            "sales_qty": sales_qty,
            "purchase_return": misc_out,
            "closing_stock": closing,
            "closing_stock_value": closing_value,
            "sales_value": sales_value,
            "division": division,
        })
    return records
