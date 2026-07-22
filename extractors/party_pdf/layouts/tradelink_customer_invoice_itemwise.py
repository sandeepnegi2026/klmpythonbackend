import re

# TRADELINK (A unit of Emmarlink Distributors) "CUSTOMER - INVOICE - ITEM WISE SALE".
#
# Customer-banded; item rows carry NO per-item value column (they end at MRP), so
# the sale amount MUST be derived as qty*rate. The per-customer 'TOTAL:' line is the
# oracle. Structure:
#   TRADELINK / DOOR NO ... / Page: N
#   CUSTOMER - INVOICE - ITEM WISE SALE
#   COMPANY : <code> KLM - <DIV>
#   Form: <d> To: <d>
#   ITCODE RACK PACK ITEM NAME BATCH QTY. FREE RATE MRP     <- header (repeats/page)
#   CUSTOMER : <code> <NAME> <TOWN>                         <- customer band
#   <DD-Mon-YY> <SB/DN/...> <NAME>                          <- invoice line
#   <ITCODE> <RACK> <PACK> <ITEM NAME...> <BATCH> <QTY> <FREE> <RATE> <MRP>
#   ...
#   TOTAL: <qty> <free> <value>                             <- per-customer footer (oracle)
#
# Un-itemized SR/CN/DN sales-returns are netted into the printed customer TOTAL but
# the returned item can still be shown as a positive sale line, so sum(qty*rate) can
# exceed the printed TOTAL. When it does, a single synthetic '[RETURN/ADJUSTMENT]'
# row (the signed residual) is emitted so the party's amount reconciles EXACTLY.

def _num(s):
    s = s.replace(",", "")
    return 0.0 if s in ("-", "") else float(s)


_SKIP = ("TRADELINK", "DOOR NO", "Page:", "CUSTOMER - INVOICE", "COMPANY",
         "Form:", "ITCODE", "Report Print")
_CUST_RE = re.compile(r"^CUSTOMER\s*:\s*(\S+)\s+(.*)$")
_INV_RE = re.compile(r"^(\d{2}-[A-Za-z]{3}-\d{2})\s+((?:SB|SR|CN|DN)/\S+)(?:\s+(.*))?$")
_INV_NOD = re.compile(r"^((?:SB|SR|CN|DN)/\S+)(?:\s+(.*))?$")
_ITEM_RE = re.compile(r"^(\d{6})\s+(.*)$")
_TOTAL_RE = re.compile(r"^TOTAL:\s+(\S+)\s+(\S+)\s+([\d.,]+)\s*$")


def parse_tradelink_customer_invoice_itemwise(text):
    headers = ["Party Name", "Area", "Invoice Date", "Invoice No",
               "Product Name", "Qty", "Free", "Rate", "Amount"]
    rows = []
    cur_party = cur_date = cur_inv = None
    cust_start = [None]

    def close_customer(printed_val):
        if cust_start[0] is None:
            return
        sale = round(sum(r[8] for r in rows[cust_start[0]:]), 2)
        if abs(sale - printed_val) > 0.005:
            rows.append([cur_party, "", cur_date, cur_inv, "[RETURN/ADJUSTMENT]",
                         0.0, 0.0, 0.0, round(printed_val - sale, 2)])
        cust_start[0] = None

    for raw in text.split("\n"):
        ln = raw.rstrip()
        if not ln.strip():
            continue
        if any(ln.startswith(s) for s in _SKIP):
            continue
        m = _CUST_RE.match(ln)
        if m:
            cur_party = m.group(2).strip()
            cur_date = cur_inv = None
            cust_start[0] = len(rows)
            continue
        m = _INV_RE.match(ln)
        if m:
            cur_date, cur_inv = m.group(1), m.group(2)
            continue
        if not _ITEM_RE.match(ln):
            m = _INV_NOD.match(ln)   # invoice line without leading date (date carries forward)
            if m:
                cur_inv = m.group(1)
                continue
        m = _ITEM_RE.match(ln)
        if m:
            toks = ln.split()
            if len(toks) < 5:
                continue
            qty = _num(toks[-4])
            free = _num(toks[-3])
            rate = _num(toks[-2])
            # product name = tokens after ITCODE/RACK/PACK, up to the last-4 numeric tail
            name_toks = toks[3:-4] if len(toks) > 7 else toks[1:-4]
            prod = " ".join(name_toks)
            rows.append([cur_party, "", cur_date, cur_inv, prod,
                         qty, free, rate, round(qty * rate, 2)])
            continue
        mt = _TOTAL_RE.match(ln)
        if mt:
            close_customer(_num(mt.group(3)))
            continue
    return headers, rows
