"""KLM "Party + Product Wise Sales" — Marg/KLM XLSX export (DUTT MEDICAL AGENCY).

A bill-detail sales report (NOT a stock report) that mis-files onto the stock_xlsx
route and, on party_xlsx, is stolen by the coarse ``party + product wise`` token into
``painkiller_partywise`` (which hard-codes offsets, maps no numeric column and yields
0 rows). This reader binds the columns by their EXACT header cells.

Three banded levels, one band per column:

    Party      | Company | Item                 | ... | Qty | Fqty | Rqty | RetQty | Rate | Value | ...
    CA012-PARAS MEDICAL POINT-ANKLESHWAR-ANKLESHWAR                                   <- party band (col0)
               | 76-KLM PEDIATRIC DIV                                                 <- company/division band (col1)
                         | 414-SOFIBAR SYNDET BAR | ... 3 | 0 | 0 | 0 | 132.2 | 396.6 <- item sale line (col2)
                         | z{{{ Company Total }}} | ... 4 | 0 | 0 | 0 |  0    | 525.17 <- company subtotal (skip)
               | z{{{ Party Total }}}                                                 <- party subtotal (skip)

Header row (row-6, exact cells):
    Party Company Item alternatename itemtype ItemShortnm batchno expdate BillNo
    BillDate Qty Fqty Rqty RetQty Rate Value NetSales NSalable

MAPPING (exact header text -> canonical; qty/value kept SEPARATE, never derived):
    Item        -> product_name   (strip leading "<code>-")
    Party band  -> party_name / party_location  (strip leading "<code>-"; trailing town)
    Company band-> division        ("76-KLM PEDIATRIC DIV" -> "KLM PEDIATRIC DIV")
    batchno     -> batch_no
    expdate     -> expiry
    BillNo      -> invoice_number
    BillDate    -> invoice_date
    Qty         -> qty
    Fqty        -> free_qty        (scheme/free)
    RetQty      -> sales_return    (return qty; Rqty is always 0 in this export)
    Rate        -> rate
    Value       -> amount

RECONCILE (this file): each product line's Value == Qty * Rate, and the per-Company /
per-Party ``z{{{ ... Total }}}`` subtotal rows equal the running Qty-sum and Value-sum of
the item lines above them (e.g. rows 9-10: qty 3+1 = 4, value 396.6+128.57 = 525.17 =
"z{{{ Company Total }}}" row). Free-only lines carry Qty 0 / Value 0 with a positive Fqty.

GATE: the compact contiguous header run
    "companyitemalternatenameitemtypeitemshortnmbatchnoexpdatebillnobilldateqtyfqty"
is unique to this export (no other corpus file carries the alternatename/itemtype/
ItemShortnm/Fqty/RetQty/NSalable column set), so it can only ever claim this report and
must sit ABOVE the coarse "party + product wise" -> painkiller_partywise rule.
"""
import re

from extractors.party_xlsx.parse_common import cell_text, compact

# A long contiguous run of the exact header cells; specific enough that no other export
# collides (alternatename/itemtype/ItemShortnm/Fqty/RetQty are unique to this format).
_HEADER_TOKEN = "companyitemalternatenameitemtypeitemshortnmbatchnoexpdatebillnobilldateqtyfqty"

_LEADING_CODE_RE = re.compile(r"^[A-Z0-9]{2,10}-")
_TOTAL_MARK = "z{{{"


def _header_idx(rows):
    for i, row in enumerate(rows[:25]):
        if _HEADER_TOKEN in compact(" ".join(cell_text(c) for c in row)):
            return i
    return None


def detect(rows):
    return _header_idx(rows) is not None


def _num(tok):
    tok = (tok or "").strip().replace(",", "")
    if not tok or tok == "-":
        return "0"
    return tok


def _split_party(text):
    """"<code>-<NAME>-<ADDRESS>-<TOWN>" band -> (trade name, town).

    Examples::
        CA012-PARAS MEDICAL POINT-ANKLESHWAR-ANKLESHWAR      -> ("PARAS MEDICAL POINT", "ANKLESHWAR")
        CA09-LIFE CURE PHARMACY-G-12 FIRST FLOOR ...-BHARUCH -> ("LIFE CURE PHARMACY", "BHARUCH")
        CA7447-MR KLM DHARMESH JIVANI--BHARUCH               -> ("MR KLM DHARMESH JIVANI", "BHARUCH")

    The party code is stripped, then the trade NAME is the FIRST dash-segment, the TOWN is
    the LAST dash-segment, and anything between them is the street address (dropped). The
    address itself may contain dashes ("G-12"), but only first+last are kept so that never
    matters."""
    raw = _LEADING_CODE_RE.sub("", text.strip()).strip()
    parts = [p.strip() for p in raw.split("-") if p.strip()]
    if not parts:
        return "", ""
    name = parts[0]
    loc = parts[-1] if len(parts) > 1 else ""
    return " ".join(name.split()), loc


def _strip_item_code(text):
    return _LEADING_CODE_RE.sub("", text.strip()).strip()


def _clean_division(text):
    raw = _LEADING_CODE_RE.sub("", text.strip()).strip()
    return " ".join(raw.split())


def parse_klm_party_product_wise_sales_xlsx(rows):
    detected = {
        "Item": "product_name",
        "Party": "party_name",
        "Company": "division",
        "batchno": "batch_no",
        "expdate": "expiry",
        "BillNo": "invoice_number",
        "BillDate": "invoice_date",
        "Qty": "qty",
        "Fqty": "free_qty",
        "RetQty": "sales_return",
        "Rate": "rate",
        "Value": "amount",
    }
    hidx = _header_idx(rows)
    if hidx is None:
        return [], detected

    header = [cell_text(c).strip() for c in rows[hidx]]

    def col(name):
        for i, h in enumerate(header):
            if h.lower() == name.lower():
                return i
        return None

    ci = {
        "item": col("Item"),
        "batch": col("batchno"),
        "exp": col("expdate"),
        "bill": col("BillNo"),
        "date": col("BillDate"),
        "qty": col("Qty"),
        "fqty": col("Fqty"),
        "retqty": col("RetQty"),
        "rate": col("Rate"),
        "value": col("Value"),
    }

    def at(cells, key):
        i = ci.get(key)
        return cells[i].strip() if (i is not None and i < len(cells)) else ""

    records = []
    current_party = current_loc = current_div = ""
    for raw in rows[hidx + 1:]:
        cells = [cell_text(c) for c in raw]
        if not any(c.strip() for c in cells):
            continue
        c0 = cells[0].strip() if len(cells) > 0 else ""
        c1 = cells[1].strip() if len(cells) > 1 else ""
        item = at(cells, "item")

        # Party band: only col0 populated (no company, no item).
        if c0 and not c1 and not item:
            current_party, current_loc = _split_party(c0)
            continue
        # Company/division band or "Party Total" marker in col1 (no item).
        if c1 and not item:
            if _TOTAL_MARK in c1 or "total" in c1.lower():
                continue
            current_div = _clean_division(c1)
            continue
        # Item / total rows live in col2.
        if not item:
            continue
        if _TOTAL_MARK in item or "total" in item.lower():
            continue
        if not current_party:
            continue

        rec = {
            "division": current_div,
            "party_name": current_party,
            "party_location": current_loc,
            "product_name": _strip_item_code(item),
            "batch_no": at(cells, "batch"),
            "expiry": at(cells, "exp"),
            "invoice_number": at(cells, "bill"),
            "invoice_date": at(cells, "date"),
            "qty": _num(at(cells, "qty")),
            "free_qty": _num(at(cells, "fqty")),
            "sales_return": _num(at(cells, "retqty")),
            "rate": _num(at(cells, "rate")),
            "amount": _num(at(cells, "value")),
        }
        records.append(rec)

    return records, detected
