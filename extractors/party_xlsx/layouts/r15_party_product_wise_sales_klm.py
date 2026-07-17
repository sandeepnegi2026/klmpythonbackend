"""
KLM / Marg "Party + Product Wise Sales" XLSX export (seen from PAARTH AGENCY / KLM,
file "KLM JUNE26.xlsx").

Structure (three-level banded)::

    PAARTH AGENCY                                               <- firm block (rows 0..4)
    Party + Product Wise Sales for period 01/06/26 to 30/06/26  <- title
    Company Group Wise Code : 06 to 06
    Run Date : ...
    Run at : HEAD OFFICE
    Area | Party | Company | Item | alternatename | itemtype | ItemShortnm |
        batchno | expdate | Qty | Fqty | Rqty | RetQty | Rate | Value | NetSales |
        NSalable | Baseamt | GstAmt | FinalAmt                  <- header row
    17-NAVSARI                                                  <- AREA band (col0 only)
      CA0024-SHREE ARIHANT CHEMIST[99]-...-NAVSARI             <- PARTY band (col1 only)
        0054-K L M  LABORATORIES LTD(PEDIA)                     <- COMPANY band (col2 only)
          000063-SOFIBAR SYNDET | .. | Shop | SOF | SKS1526 | 31/03/2028 |
              1 | 0 | 0 | 0 | 138.98 | 138.98 | ...             <- product line (col3=Item)
        z{{{ Company Total }}} | 1 | ...                        <- subtotal (skip)
      z{{{ Party Total }}}                                      <- subtotal (skip)
    Z{{{ Grand Total }}}                                        <- grand total (skip)

The AREA sits in col0, the PARTY (with customer code, phone-code, address, town) in
col1, the COMPANY/division in col2, and the product code-name in col3. Every product
line carries: Qty (col9), Fqty=free (col10), Rqty (col11), RetQty=sales return (col12),
Rate (col13) and Value=gross line value (col14, == Qty*Rate). Subtotal / grand-total
band rows are wrapped in ``z{{{ ... Total }}}`` / ``Z{{{ Grand Total }}}`` and skipped.

The generic header maps several columns via the shared synonym set, but the file
currently mis-detects to ``painkiller_partywise`` and extracts every numeric as zero
(RED, COLUMN_MISALIGNMENT). Detection here is gated hard on BOTH the distinctive
compact title token ``partyproductwisesales`` AND the exact contiguous header run
``alternatenameitemtypeitemshortnm`` (columns no other corpus format carries), so it
can only ever claim this specific export.
"""
import re

from extractors.party_xlsx.parse_common import cell_text, compact

# Compact (normalize + no-space) title fingerprint unique to this KLM/Marg export.
_TITLE_SIG = "partyproductwisesales"
# Exact contiguous header run (compact). The leading ``areapartycompanyitem`` prefix +
# the ``expdateqtyfqty`` tail (NO BillNo/BillDate between them) makes this mutually
# exclusive with the 2-level DUTT variant (r15_klm_party_product_wise_sales_xlsx), whose
# header is "...expdate BillNo BillDate Qty Fqty..." and has no leading Area column.
_HDR_SIG = "areapartycompanyitemalternatenameitemtypeitemshortnmbatchnoexpdateqtyfqty"

# Product code-name pattern: leading alnum code, a hyphen, then the description.
_CODE_RE = re.compile(r"^[0-9A-Za-z]+-")
# Total / grand-total band markers ("z{{{ Company Total }}}" etc.).
_TOTAL_RE = re.compile(r"\{\{\{.*total.*\}\}\}", re.IGNORECASE)

# Fixed column indices (0-based) for product rows in this export.
_C_AREA = 0
_C_PARTY = 1
_C_COMPANY = 2
_C_ITEM = 3
_C_QTY = 9
_C_FREE = 10
_C_RQTY = 11
_C_RETQTY = 12
_C_RATE = 13
_C_VALUE = 14


def _is_number(text):
    if text is None:
        return False
    t = str(text).strip()
    if not t:
        return False
    return bool(re.fullmatch(r"-?\d[\d,]*\.?\d*", t))


def _title_present(rows):
    blob = compact(" ".join(cell_text(c) for r in rows[:8] for c in r))
    return _TITLE_SIG in blob


def _header_idx(rows):
    """Row index of the ``Area | Party | Company | Item | alternatename | ...`` header."""
    for idx, row in enumerate(rows[:25]):
        if _HDR_SIG in compact(" ".join(cell_text(c) for c in row)):
            return idx
    return None


def detect(rows):
    """True only for the KLM/Marg "Party + Product Wise Sales" export.

    Requires BOTH the title fingerprint and the exact ``alternatename itemtype
    ItemShortnm`` header run, plus at least a couple of code-prefixed product rows
    that carry a numeric Qty, so a plain columnar file can never be diverted.
    """
    if not _title_present(rows):
        return False
    hidx = _header_idx(rows)
    if hidx is None:
        return False
    prods = 0
    for raw in rows[hidx + 1 : hidx + 300]:
        cells = [cell_text(c) for c in raw]
        item = cells[_C_ITEM].strip() if len(cells) > _C_ITEM else ""
        if not item or not _CODE_RE.match(item):
            continue
        if _TOTAL_RE.search(item):
            continue
        qty = cells[_C_QTY] if len(cells) > _C_QTY else ""
        if _is_number(qty):
            prods += 1
    return prods >= 2


def parse_party_product_wise_sales_klm(rows):
    hidx = _header_idx(rows)
    if hidx is None:
        return [], {}

    records = []
    current_area = ""
    current_party = ""
    current_company = ""

    for raw in rows[hidx + 1 :]:
        cells = [cell_text(c) for c in raw]

        def g(i):
            return cells[i].strip() if len(cells) > i else ""

        c0, c1, c2, item = g(_C_AREA), g(_C_PARTY), g(_C_COMPANY), g(_C_ITEM)

        # subtotal / grand-total band rows -> skip entirely
        joined = " ".join(cells)
        if _TOTAL_RE.search(joined):
            continue

        # AREA band: text only in col0
        if c0 and not c1 and not c2 and not item:
            current_area = c0
            continue
        # PARTY band: text only in col1
        if c1 and not c0 and not c2 and not item:
            current_party = c1
            continue
        # COMPANY band: text only in col2
        if c2 and not c0 and not c1 and not item:
            current_company = c2
            continue

        # product line: col3 carries a code-prefixed item name + a numeric Qty
        if not item or not _CODE_RE.match(item):
            continue
        qty = g(_C_QTY)
        if not _is_number(qty):
            continue
        if not current_party:
            continue

        rec = {
            "party_name": current_party,
            "product_name": item,
            "qty": qty,
        }
        if current_area:
            rec["party_location"] = current_area
        if current_company:
            rec["division"] = current_company

        free = g(_C_FREE)
        if _is_number(free) and free not in ("0", "0.0"):
            rec["free_qty"] = free
        retqty = g(_C_RETQTY)
        if _is_number(retqty) and retqty not in ("0", "0.0"):
            rec["return_qty"] = retqty
        rate = g(_C_RATE)
        if _is_number(rate):
            rec["rate"] = rate
        value = g(_C_VALUE)
        if _is_number(value):
            rec["amount"] = value

        records.append(rec)

    detected = {
        "Area": "party_location",
        "Party": "party_name",
        "Company": "division",
        "Item": "product_name",
        "Qty": "qty",
        "Fqty": "free_qty",
        "RetQty": "return_qty",
        "Rate": "rate",
        "Value": "amount",
    }
    return records, detected
