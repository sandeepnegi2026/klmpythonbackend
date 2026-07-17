import re

from extractors.stock_pdf.parse_common import _skip_line, _split_product_pack

# ---------------------------------------------------------------------------
# KLM "STOCK AND SALES STATEMENT" — Code / LM-SALE / Receipts / AGE dialect
# (HEMA SUNDHAR MEDICAL AGENCIES; one file per KLM division:
#  COSMO / COSMO CORE / DERMACOR / PEDIA / PHARMA ...).
#
# Two-line header:
#   Code Product Name Packing LM Opening Receipts Total Sales Closing Closing AGE
#                              SALE                        Stock   Stock  Value
#
# Every product row carries a LEADING item CODE (KLM394 / KL1004 / KLC001 /
# LMC512) and a FIXED trailing run of EIGHT numbers (zero cells print '0'):
#
#   [0] LM SALE   (last-month sale — informational, dropped)
#   [1] Opening
#   [2] Receipts  -> purchase_stock (inflow)
#   [3] Total     (Opening + Receipts cross-check — dropped)
#   [4] Sales     -> sales_qty (outflow)
#   [5] Closing Stock        -> closing_stock (QTY)
#   [6] Closing Stock Value  -> closing_stock_value (RUPEES, has decimals)
#   [7] AGE       (days — informational, dropped)
#
# Reconcile identity (verified on all example files):
#   Opening + Receipts - Sales == Closing Stock.
# closing_stock_value is a rupee column and is NEVER treated as a qty.
#
# The generic fallback mis-reads this export: it peels AGE into closing_stock
# and drops both the real Closing qty and the Closing Value -> false SANITY.
#
# This is a distinct dialect from the batch-wise sibling
# (stock_batchwise_statement) which shares the 'Opening Receipts Total Sales
# Closing Closing' run but adds a BATCH+EXP block (…closing closing VALUE, no
# AGE) and carries no Code / LM SALE columns. The detect gate keys on the
# '…closing closing AGE' terminus, which is disjoint from that sibling's
# '…closing closing Value' run, so neither gate steals the other.
# ---------------------------------------------------------------------------

# Local comma-tolerant numeric token: 1,987.00 / 0.00 / -1 / 170,733.77
_NUM_TOK_RE = re.compile(r"^-?\d[\d,]*(?:\.\d{1,2})?$")

# Leading item CODE: 2-3 leading letters + alnum, must contain a digit
# (KLM394, KL1004, KLC001, KLD001, KL0009, LMC512, KL3010). A genuine product
# first word is a plain letter word (no digit), so this never eats a name.
_CODE_RE = re.compile(r"^[A-Z]{2,3}[A-Z0-9]*\d[A-Z0-9]*$")


def _is_num(t):
    return bool(_NUM_TOK_RE.match(t))


def _to_f(t):
    return float(t.replace(",", ""))


def _peel_tail(s):
    """Split ``s`` into (lead_text, [float, ...]) peeling the trailing numeric run
    with the local comma-tolerant token regex."""
    toks = s.split()
    tail = []
    while toks and _is_num(toks[-1]):
        tail.insert(0, _to_f(toks.pop()))
    return " ".join(toks), tail


def _is_header(compact):
    # first header line compacts to
    # 'codeproductnamepackinglmopeningreceiptstotalsalesclosingclosingage'
    return "openingreceiptstotalsalesclosingclosingage" in compact


def parse_klm_lmsale_receipts_age(text):
    """KLM 'STOCK AND SALES STATEMENT' — Code/LM-SALE/Receipts/AGE dialect.

    8 trailing numbers per row:
        LM_SALE, Opening, Receipts, Total, Sales, Closing_Stock,
        Closing_Stock_Value, AGE
    Mapping (positional; qty is NEVER derived from the value column):
        opening_stock=Opening, purchase_stock=Receipts, sales_qty=Sales,
        closing_stock=Closing_Stock, closing_stock_value=Closing_Stock_Value.
    Identity: Opening + Receipts - Sales == Closing_Stock.
    """
    records = []
    started = False
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        low = s.lower()
        compact = low.replace(" ", "")

        # data begins after the (two-line) column header
        if _is_header(compact):
            started = True
            continue
        if not started:
            continue

        # footer / band / separator noise
        if _skip_line(s):
            continue
        # 'SALE Stock Stock Value' header continuation line
        if low.startswith("sale stock"):
            continue
        # value-summary footer ('Opening Value Rs. ...', 'Sales Value Rs. ...')
        if "value rs." in low:
            continue

        lead, vals = _peel_tail(s)
        if len(vals) != 8:
            continue
        lead = lead.strip()
        if not lead:
            continue

        # peel the leading item CODE token off the lead
        code = ""
        toks = lead.split()
        if toks and _CODE_RE.match(toks[0]):
            code = toks[0]
            lead = " ".join(toks[1:]).strip()
        if not lead:
            continue

        opening = vals[1]
        receipts = vals[2]
        sales = vals[4]
        closing = vals[5]
        closing_value = vals[6]

        name, pack = _split_product_pack(lead)
        rec = {
            "product_name": name,
            "pack": pack,
            "opening_stock": opening,
            "purchase_stock": receipts,
            "sales_qty": sales,
            "closing_stock": closing,
            "closing_stock_value": closing_value,
        }
        if code:
            rec["product_code"] = code
        records.append(rec)
    return records
