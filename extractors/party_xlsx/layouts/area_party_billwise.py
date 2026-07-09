"""
"Area/Party/Billwise Sales" — a multi-level code+name register (e.g. RAMAKRISHNA).

Every row begins with a numeric code in column 0; the level is told apart by content:

    141   KLM Laboratories Pvt Ltd -Pead                      <- division marker (name only)
    01    MYSORE                                              <- area marker (name only)
    1299  Eshwar Medicals(RJN)  …R.S.Naidunagar…Rajendranagar <- party band (name + address)
    159006 KLM D3 Nano Drops 15ml 02-05-26 C-3289 … 2 … 178.58 <- product line (date + qty)
                       Cus. Total                       178.58 <- per-party subtotal

The customer sits in the ``Name`` column of a **party band** — a row whose ``Date``
column is not a real date and whose ``Qty`` is not numeric, but which carries address
text in the trailing columns. Product lines (real date + numeric qty) below it inherit
that party. Division/area marker rows (name only, no address) are skipped, as are the
``Cus. Total`` subtotals. The generic ``tabular`` reader cannot attach the party here
because it is a band, not a column.
"""
from core.header_match import normalize

from extractors.party_xlsx.parse_common import cell_text, is_numeric_qty, is_subtotal, looks_like_date

_TITLE = "area party billwise"
_TOTAL = ("cus. total", "cus.total", "customer total", "grand total", "total")


def title_matches(rows):
    head = normalize(" ".join(" ".join(cell_text(c) for c in r) for r in rows[:8]))
    return _TITLE in head


def _find_header(rows):
    for idx, row in enumerate(rows[:15]):
        norm = [normalize(c) for c in row]
        if "code" in norm and "name" in norm and "qty" in norm:
            return idx
    return None


def detect(rows):
    return title_matches(rows) and _find_header(rows) is not None


def parse_area_party_billwise(rows):
    header_idx = _find_header(rows)
    if header_idx is None:
        return [], {}
    norm = [normalize(c) for c in rows[header_idx]]

    def col(*names):
        for n in names:
            if n in norm:
                return norm.index(n)
        return None

    name_i = col("name")
    date_i = col("date")
    qty_i = col("qty")
    pack_i = col("packing", "pack")
    bill_i = col("bill no", "billno")
    batch_i = col("batch no", "batchno", "batch")
    rate_i = col("rate")
    val_i = col("value")
    if name_i is None or date_i is None or qty_i is None:
        return [], {}

    def at(cells, i):
        return cells[i] if (i is not None and i < len(cells)) else ""

    records = []
    current_party = ""
    current_area = ""
    for raw in rows[header_idx + 1:]:
        cells = [cell_text(c) for c in raw]
        if not any(cells):
            continue
        low = " ".join(cells).lower()
        if any(t in low for t in _TOTAL) or is_subtotal(cells[0]):
            continue
        name = at(cells, name_i)
        date = at(cells, date_i)
        qty = at(cells, qty_i)
        if not name:
            continue

        # product line: real date + numeric qty
        if looks_like_date(date) and is_numeric_qty(qty):
            if not current_party:
                continue
            records.append({
                "party_name": current_party,
                "party_location": current_area,
                "product_name": name,
                "pack": at(cells, pack_i),
                "invoice_date": date,
                "invoice_number": at(cells, bill_i),
                "batch_no": at(cells, batch_i),
                "qty": qty,
                "rate": at(cells, rate_i),
                "amount": at(cells, val_i),
            })
            continue

        # band row: distinguish a party (carries an address in the trailing columns)
        # from a division/area marker (a bare code+name with nothing after it).
        address = [cells[j] for j in range(date_i, min(len(cells), qty_i + 1))
                   if at(cells, j) and not looks_like_date(cells[j]) and not is_numeric_qty(cells[j])]
        if address:
            current_party = name.strip()
            current_area = address[-1].strip().strip(",")

    detected = {"Name": "party_name", "Date": "invoice_date", "Qty": "qty",
                "Rate": "rate", "Value": "amount", "Bill No.": "invoice_number"}
    return records, detected
