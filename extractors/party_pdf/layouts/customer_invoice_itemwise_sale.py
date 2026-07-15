"""MALU MEDICO — Marg "CUSTOMER - INVOICE - ITEM WISE SALE" (billwise).

Vendor : MALU MEDICO PRIVATE LIMITED (SANGLI). Report is a KLM division
billwise sale detail with a 3-level band structure:

    CUSTOMER : <code> <NAME + AREA/ADDRESS> [<GSTIN>]      <- customer band
    <dd-Mon-yy> SB/<n> TAXABLE AMT :.. GST AMT :.. INVOICE VALUE :..  <- invoice sub-band
    <COMPNAME> <PACK> <ITEM NAME> <BATCH> QTY SCM% RATE MRP NETAMT     <- item line
    ...
    TOTAL: <qtysum> - <invoicevaluesum>                    <- per-customer roll-up (skip)

One output row per ITEM line. The item line's flat text is regular: it always
starts with a COMPNAME token (KLM-C / KLM-D / KLM-P) and ends with exactly five
numeric tokens — QTY., SCM%, RATE, MRP, NET AMT. Everything between COMPNAME and
that numeric run is PACK + ITEM NAME + BATCH, where:

  * BATCH  = the LAST text token before the numeric run (an alphanumeric code
             like AF519 / BC524. / SKS0726 / EAN07AAA / KLP26002).
  * PACK   = the size cell right after COMPNAME — either two tokens
             "<num> <UNIT>" (e.g. "30 GM", "10 TAB") or a single glued token
             (e.g. "100GM", "10X5ML", "10X1GM", "SACHET").
  * ITEM NAME = the tokens between PACK and BATCH (e.g. "NIOSOL OINT").

Column map:
    CUSTOMER band  -> party_name  (leading numeric code + trailing 15-char GSTIN
                                    stripped; the free-form area/address that
                                    follows the name is NOT cleanly delimited, so
                                    it is left in party_name rather than guessed)
    SB/<n>         -> invoice_number      dd-Mon-yy -> invoice_date (carried
                                          forward when an invoice line omits it)
    ITEM NAME      -> product_name        PACK      -> pack        BATCH -> batch_no
    QTY.           -> qty                 RATE      -> rate        MRP   -> mrp
    NET AMT        -> amount              SCM%      -> discount_percent (a %, not
                                          a free qty — free stays 0)

Reconcile (file tail "GRAND TOTAL: ... TAX AMT ... INVOICE AMT"): NET AMT is the
taxable-side amount, so sum(NET AMT) == the printed GRAND TOTAL "TAXABLE AMT".
For MALU MEDICO May: 1034 item rows, sum(qty)=3863, sum(NET AMT)=484668.23 ==
GRAND TOTAL TAXABLE AMT 484668.23 (exact). The per-customer "TOTAL: N - V" line
carries the qty sum (N) and the INVOICE VALUE sum (V = taxable + GST), not NET
AMT, so it is a roll-up only and is skipped.
"""

import re

# 'Sch Per' (SCM% column) maps to discount_percent — SCM% is a scheme PERCENT,
# not a free quantity, so it must NOT land in free_qty (a bare "%"/"Scheme %"
# header would). 'CompName' maps to no canonical key (dropped by design).
H = ['Party Name', 'Party Location', 'Party GSTIN', 'Invoice Number',
     'Invoice Date', 'CompName', 'Pack', 'Product Name', 'Batch',
     'Qty', 'Sch Per', 'Rate', 'MRP', 'Amount']

# COMPNAME anchor at the head of every item line.
_COMP = re.compile(r'^KLM-[A-Z0-9]+$')
# A numeric cell (qty / scm% / rate / mrp / net amt), optional sign/decimal.
_NUM = re.compile(r'^-?\d+(?:\.\d+)?$')
# Unit word for a two-token pack ("30 GM").
_UNIT = re.compile(r'^(?:GM|ML|MG|TAB|CAP|GUMM|GUM|PC|PCS|SACHET)$', re.I)
# A glued single-token pack ("100GM", "10X5ML", "10X1GM", "10TAB", "SACHET").
_PACK_GLUED = re.compile(r'^(?:SACHET|\d+(?:X\d+)?[A-Z]+)$', re.I)
# Customer band: "CUSTOMER : <code> <rest>".
_CUST = re.compile(r'^CUSTOMER\s*:\s*(\d+)\s+(.+)$')
# Invoice sub-band: "[<dd-Mon-yy> ]SB/<n> TAXABLE AMT ...".
_INV = re.compile(
    r'^(?:(\d{1,2}-[A-Za-z]{3,}-\d{2,4})\s+)?([A-Z]{1,4}/\d+)\s+TAXABLE\s+AMT',
    re.I,
)
# A complete 15-char GSTIN (2 digits + 10 PAN + 3) trailing the customer band.
# Truncated fragments (e.g. "27AXGPP736") are part of a cut-off address and are
# intentionally NOT stripped — only a full, well-formed GSTIN is peeled.
_GSTIN = re.compile(r'^\d{2}[A-Z]{5}\d{4}[A-Z]\d[A-Z\d]{2}$')


def _split_customer(rest):
    """`<NAME + AREA/ADDRESS> [<GSTIN>]` -> (party, gstin).

    The name and the free-form area/address run together with no delimiter, so a
    reliable name/area split is impossible; the whole string (sans a trailing
    full GSTIN) is kept as the party name."""
    toks = rest.split()
    gstin = ''
    if toks and _GSTIN.match(toks[-1]):
        gstin = toks[-1]
        toks = toks[:-1]
    return ' '.join(toks).strip(), gstin


def parse_customer_invoice_itemwise_sale(text):
    rows = []
    party = gstin = ''
    inv_no = inv_date = ''

    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            continue

        m = _CUST.match(s)
        if m:
            party, gstin = _split_customer(m.group(2))
            inv_no = inv_date = ''          # new customer resets the invoice band
            continue

        m = _INV.match(s)
        if m:
            if m.group(1):
                inv_date = m.group(1)       # carry forward when a later line omits it
            inv_no = m.group(2)
            continue

        toks = s.split()
        if not _COMP.match(toks[0]):
            continue                        # TOTAL:, page furniture, headers, etc.

        # Trailing numeric run = QTY. SCM% RATE MRP NET AMT (>=5 numbers).
        k = len(toks)
        while k > 0 and _NUM.match(toks[k - 1]):
            k -= 1
        nums = toks[k:]
        if len(nums) < 5:
            continue
        qty, scm, rate, mrp, netamt = nums[-5], nums[-4], nums[-3], nums[-2], nums[-1]

        text_toks = toks[:k]                # COMPNAME PACK ITEM... BATCH
        if len(text_toks) < 3:
            continue
        comp = text_toks[0]
        batch = text_toks[-1]
        middle = text_toks[1:-1]            # PACK + ITEM NAME

        # Peel PACK off the front of the middle span.
        pack = ''
        if len(middle) >= 2 and re.fullmatch(r'\d+', middle[0]) and _UNIT.match(middle[1]):
            pack = middle[0] + ' ' + middle[1]
            item = ' '.join(middle[2:]).strip()
        elif middle and _PACK_GLUED.match(middle[0]):
            pack = middle[0]
            item = ' '.join(middle[1:]).strip()
        else:
            item = ' '.join(middle).strip()

        if not item:
            continue

        rows.append([
            party, '', gstin, inv_no, inv_date,
            comp, pack, item, batch,
            qty, scm, rate, mrp, netamt,
        ])

    return H, rows
