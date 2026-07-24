"""
KLM LAB per-division party sale export — "Retailer:" banded (THANE MEDICAL AGENCY).

A single-sheet workbook, one book per division (COSMO DIVISION, PHARMA, ...), whose
header row is::

    Manufacturer | Area | City | Invoice Date | Invoice No | Name | Qty | Free | Gross Amt | CGSTRs | SGSTRs

and whose customer (party) is a *band row*, not a column::

    Manufacturer | Area | City | Invoice Date | Invoice No | Name | Qty | Free | Gross Amt | CGSTRs | SGSTRs   <- header (row 0)
    Retailer: AADARSH MEDICAL & GEN STRS : R61 Total=168                                                      <- PARTY band (single cell)
    KLM LAB (COSMO DIVISION) | KHOPAT | THANE (W) | 2026-06-09 ... | 029286 | KLM-D3 60K 8CAP | 1 | 0 | 167.86 | 4.2 | 4.2   <- sale line
    Retailer: AARAV MEDICAL : R436004 Total=225                                                               <- next PARTY band
    KLM LAB (COSMO DIVISION) |  | BHIWANDI 421302 | 2026-06-15 ... | 031885 | KLFLAM-SP | 3 | 0 | 225 | 5.46 | 5.46
    ...

Row taxonomy:
  * PARTY band : one cell "Retailer: <NAME> : <RetailerCode> Total=<amount>" -> set the
    current party (the trailing ``Total=`` is the party's Gross-Amt subtotal — verified to
    equal the rounded sum of the following sale lines' Gross Amt, so it is NOT emitted).
  * sale line  : the ``Manufacturer`` cell carries "KLM LAB (...)"; the ``Name`` column is
    the PRODUCT (e.g. "KLM-D3 60K 8CAP") — NOT a customer — so the generic header mapper's
    ``Name`` -> ``vendor_name`` guess is wrong and the file falls to ``tabular`` with an empty
    party_name (-> RED MISSING_REQUIRED_FIELD:party_name).

This layout supplies the two missing pieces: it carries the band party down onto every sale
line, and it maps the deceptively-named ``Name`` column POSITIONALLY to ``product_name``.

Value columns: ``Gross Amt`` is the line value -> ``amount`` (what triage total-reconcile
reads) and the required ``taxable_value``; ``Qty``/``Free`` stay their own columns (qty is
never derived from a value column); ``rate`` = Gross Amt / Qty. ``Area`` -> ``party_location``
(``City`` is the fallback). ``Invoice No`` / ``Invoice Date`` are kept per line.

Gated on the exact ``… Name Qty Free Gross Amt CGSTRs SGSTRs`` header run (the
``cgstrssgstrs`` token pair is unique across the corpus) PLUS at least one ``Retailer:``
band row, so it claims only this export and nothing else is diverted.
"""
import re

from extractors.party_xlsx.parse_common import cell_text, compact, is_subtotal

# Compact header signature. "grossamt" + the "cgstrssgstrs" (CGSTRs immediately before
# SGSTRs) run appears in no other party_xlsx header, so the gate cannot steal another file.
_HEADER_TOKENS = ("name", "qty", "free", "grossamt", "cgstrs", "sgstrs")

# "Retailer: <NAME> : <CODE> Total=<amount>" band. The party is everything between the
# leading "Retailer:" and the final " : <code> Total=" tail (names may carry '.', '&', etc.).
_BAND_RE = re.compile(r"^\s*retailer\s*:\s*(.*?)\s*:\s*\S+\s+total\s*=", re.IGNORECASE)


def _header_idx(rows):
    """Row index of the ``… Name Qty Free Gross Amt CGSTRs SGSTRs`` header, or None."""
    for idx, row in enumerate(rows[:15]):
        head = compact(" ".join(cell_text(c) for c in row))
        if all(tok in head for tok in _HEADER_TOKENS):
            return idx
    return None


def _has_retailer_band(rows, header_idx):
    for row in rows[header_idx + 1 : header_idx + 400]:
        if row and _BAND_RE.match(cell_text(row[0])):
            return True
    return False


def detect(rows):
    """True only for the KLM LAB "Retailer:" banded per-division party export.

    Requires BOTH the exact ``Name Qty Free Gross Amt CGSTRs SGSTRs`` header run and at
    least one ``Retailer: <name> : <code> Total=`` band row — a combination carried by no
    other corpus file — so no currently-passing layout is diverted.
    """
    header_idx = _header_idx(rows)
    if header_idx is None:
        return False
    return _has_retailer_band(rows, header_idx)


def _to_float(value):
    text = cell_text(value).replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_retailer_band_cgst_sgst(rows):
    header_idx = _header_idx(rows)
    if header_idx is None:
        return [], {}

    # Column positions are fixed by the header run (mapped positionally, not by fuzzy
    # synonyms): the deceptive "Name" column is the PRODUCT, not a customer.
    headers = [compact(cell_text(c)) for c in rows[header_idx]]
    idx_of = {}
    for want in ("area", "city", "invoicedate", "invoiceno", "name", "qty", "free", "grossamt"):
        for i, h in enumerate(headers):
            if h == want and want not in idx_of:
                idx_of[want] = i

    def get(cells, key):
        i = idx_of.get(key)
        return cell_text(cells[i]) if (i is not None and i < len(cells)) else ""

    records = []
    current_party = ""
    for raw in rows[header_idx + 1 :]:
        if not raw:
            continue
        first = cell_text(raw[0])

        band = _BAND_RE.match(first)
        if band:
            name = band.group(1).strip()
            if name and not is_subtotal(name):
                current_party = name
            continue

        product = get(raw, "name")
        qty = get(raw, "qty")
        free = get(raw, "free")
        amount = get(raw, "grossamt")
        # A sale line needs a product plus at least one figure. Guards against blank
        # spacer rows and any stray non-band, non-sale text.
        if not product or is_subtotal(product):
            continue
        if not (qty.strip() or amount.strip()):
            continue
        if not current_party:
            continue

        record = {
            "party_name": current_party,
            "product_name": product,
            "qty": qty,
            "free_qty": free,
            "amount": amount,
            # No separate taxable column; Gross Amt is the line net value.
            "taxable_value": amount,
        }
        area = get(raw, "area") or get(raw, "city")
        if area:
            record["party_location"] = area
        inv = get(raw, "invoiceno")
        if inv:
            record["invoice_number"] = inv
        inv_date = get(raw, "invoicedate")
        if inv_date:
            record["invoice_date"] = inv_date
        amt_f, qty_f = _to_float(amount), _to_float(qty)
        if amt_f is not None and qty_f:
            record["rate"] = round(amt_f / qty_f, 4)
        records.append(record)

    detected = {
        "Name": "product_name",
        "Qty": "qty",
        "Free": "free_qty",
        "Gross Amt": "amount",
        "Area": "party_location",
        "Invoice No": "invoice_number",
        "Invoice Date": "invoice_date",
    }
    return records, detected
