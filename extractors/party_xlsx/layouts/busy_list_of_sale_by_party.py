"""
"List of Sale By Party" — Busy ERP party-wise sale export (MODI PHARMA / KLM).

A PARTY-banded layout with a serial-number outline in col0 (``Sr.``):

    MODI PHARMA
    List of Sale By Party
    Mfr:KLM   >> KLM
    Date From 01/05/2026 to 31/05/2026
    Sr.  Date        DocNo          Item Name              Qty Free  MRP     Sch% Value  Amount  <- header
    1                               ABHA MEDICAL STORES  BALGI                                   <- PARTY band (integer Sr.)
    1.1  2026-05-11.. 2627-SL-01816 Kenz-sal Lotion {60ml}  1        292.00i      204.4  214.62   <- product line (N.M Sr.)
    1.2  2026-05-25.. 2627-SL-02400 Strianil Gel Cream ...  1        299.50i      198.99 234.81
         (blank Sr.)                Total: of ABHA ...       2                    403.39 449.43   <- per-party subtotal -> skip

The customer (party) is the ``Item Name`` cell on the INTEGER-``Sr.`` band row; the product lines
are the ``N.M``-``Sr.`` rows beneath it. The generic ``customer_product_banded`` reader mis-binds
this: it takes the ``Sr.`` serial ("1", "2", ...) as the party and drops every real shop name. This
reader recovers the real party from the band and maps the labelled columns by header name.

Gated on the compact title token "listofsalebyparty" (present in rows[:6]) — proven to match ONLY
MODI's two files in the corpus, so every other layout is byte-for-byte unaffected. MUST be detected
before ``customer_product_banded``.
"""
import re

from extractors.party_xlsx.parse_common import cell_text, compact

_INT_SR = re.compile(r"^\d+$")
_SUB_SR = re.compile(r"^\d+\.\d+$")


def _col_map(header_row):
    """Map canonical roles to column indices by matching the header cell labels."""
    idx = {}
    for i, c in enumerate(header_row):
        k = compact(cell_text(c))
        if k == "sr" or k == "srno":
            idx.setdefault("sr", i)
        elif k == "date":
            idx.setdefault("date", i)
        elif k == "docno":
            idx.setdefault("docno", i)
        elif k == "itemname":
            idx.setdefault("item", i)
        elif k == "qty":
            idx.setdefault("qty", i)
        elif k == "free":
            idx.setdefault("free", i)
        elif k == "mrp":
            idx.setdefault("mrp", i)
        elif k == "value":
            idx.setdefault("value", i)
        elif k == "amount":
            idx.setdefault("amount", i)
    return idx


def _header_idx(rows):
    for i, row in enumerate(rows[:15]):
        c = compact(" ".join(cell_text(x) for x in row))
        if "sr" in c and "itemname" in c and "qty" in c:
            return i
    return None


def detect(rows):
    head = compact(" ".join(" ".join(cell_text(c) for c in r) for r in rows[:6]))
    if "listofsalebyparty" not in head:
        return False
    hidx = _header_idx(rows)
    if hidx is None:
        return False
    idx = _col_map(rows[hidx])
    # Must carry the two columns that define the layout: a Sr. outline and an Item Name.
    return "sr" in idx and "item" in idx


def parse_busy_list_of_sale_by_party(rows):
    detected = {"Item Name": "product_name", "Qty": "qty", "Free": "free_qty",
                "MRP": "mrp", "Amount": "amount", "Value": "taxable_value",
                "DocNo": "invoice_number", "Date": "invoice_date"}
    hidx = _header_idx(rows)
    if hidx is None:
        return [], detected
    idx = _col_map(rows[hidx])
    sr_i, item_i = idx.get("sr"), idx.get("item")
    if sr_i is None or item_i is None:
        return [], detected

    def g(cells, key):
        i = idx.get(key)
        return cells[i].strip() if (i is not None and i < len(cells)) else ""

    records, party = [], ""
    for row in rows[hidx + 1:]:
        cells = [cell_text(c) for c in row]
        sr = (cells[sr_i].strip() if sr_i < len(cells) else "")
        item = (cells[item_i].strip() if item_i < len(cells) else "")
        if not item:
            continue
        if item.upper().startswith("TOTAL"):        # per-party / grand subtotal
            continue
        if _INT_SR.match(sr):                        # PARTY band row
            party = item
            continue
        if _SUB_SR.match(sr):                        # product line
            if not party:
                continue
            amt = g(cells, "amount") or g(cells, "value")
            rec = {
                "party_name": party,
                "product_name": item,
                "qty": g(cells, "qty").replace(",", ""),
                "free_qty": (g(cells, "free") or "0").replace(",", ""),
                "amount": amt.replace(",", ""),
            }
            mrp = g(cells, "mrp")
            if mrp:
                rec["mrp"] = mrp
            val = g(cells, "value")
            if val:
                rec["taxable_value"] = val.replace(",", "")
            inv = g(cells, "docno")
            if inv:
                rec["invoice_number"] = inv
            records.append(rec)
    return records, detected
