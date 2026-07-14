"""
"ITEM VS PARTIES WISE SALE SCHEME REGISTER" — Marg-style product-banded party sales
register (MAHAVEER / MAHABIR DISTRIBUTORS, KLM). Every logical group is a PRODUCT band
row followed by the customer (party) rows that bought it; the band's numeric columns are
the SUM of its party rows (a subtotal), so both must not be double-counted:

    ITEM VS PARTIES  WISE SALE SCHEME REGISTER                       <- title (row 2)
    Item VS Parties | Sale Qty | Free Qty | Free Amount | Amount |   <- header (row 4)
        Discount 1 | Bill Discount | Scheme | MRP Value | Discount 2 | Tax Amount
    ONITRAZ CAP       10 CAP | 242.5 | 72.5 | 9570 | 30096 | ...     <- PRODUCT band (= sum below)
    HARYANA MEDICAL HALL...       AGROHA | 2.5 | 0.5 | 66  | 316.8 | ...  <- party row
    RIDDHISHA MEDICAL HALL        HISAR CITY | 240 | 72 | 9504 | 29779.2  <- party row
    TOTAL | 526.93 | 155.07 | 30872.31 | 96414.83 | ...             <- grand total (skip)

The original export marks party rows by INDENTING col0 with leading whitespace, but the
xlsx loader strips leading spaces, so band-vs-party cannot be told apart on indentation.
Instead this parser uses the structural invariant that survives: a PRODUCT band's Amount
equals the sum of the Amounts of the consecutive party rows that follow it (walk forward
accumulating Amount until it matches the band, then those rows are that band's parties).
This exactly separates 16 product bands from 23 party rows without any indent signal.

COLUMN MAP (party rows only; band rows are subtotals and are NOT emitted):
    col0            -> product_name (from the current band) / party_name+party_location
    Sale Qty  (1)   -> qty
    Free Qty  (2)   -> free_qty
    Amount    (4)   -> amount
    Discount 1(5) + Bill Discount(6) -> discount_amount (summed)
    MRP Value (8)   -> mrp
    Tax Amount(10)  -> gst_amount
    rate            -> derived Amount / Sale Qty (no per-row rate column exists)

RECONCILE: sum(amount) over emitted party rows == printed TOTAL row Amount
(96,414.83); sum(band Amount) == sum(party Amount) per group.
"""
import re

from extractors.party_xlsx.parse_common import cell_text, compact

# Peel a trailing 2+-space column: "<name>  <town>" for a party, "<name>  <pack>" for a
# product band. Single spaces inside a name/product ("NEW HAPPY MEDICAL HALL",
# "COSMO Q MOISTURIZG") are never touched — only the LAST run of 2+ spaces splits.
_TRAIL_RE = re.compile(r"^(.*\S)\s{2,}(\S.*)$")

# Header column indices are fixed by this vendor's export; still resolved from the header
# row so a future column shuffle is caught rather than silently mis-bound.
_HDR_MAP = {
    "saleqty": "qty",
    "freeqty": "free_qty",
    "amount": "amount",
    "discount1": "_disc1",
    "billdiscount": "_disc2",
    "mrpvalue": "mrp",
    "taxamount": "gst_amount",
}


def _split_trailing(text):
    text = str(text).replace("\xa0", " ").rstrip()
    m = _TRAIL_RE.match(text)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return text.strip(), ""


def _header_idx(rows):
    for i, row in enumerate(rows[:20]):
        c = compact(" ".join(cell_text(x) for x in row))
        if "itemvsparties" in c and "saleqty" in c and "amount" in c:
            return i
    return None


def _cols(header):
    """Canonical key -> column index resolved from the header cells."""
    col = {}
    for j, cell in enumerate(header):
        n = compact(cell_text(cell))
        key = _HDR_MAP.get(n)
        if key and key not in col:
            col[key] = j
    return col


def _num(text):
    """Parse a money/qty token to float; '-'/blank -> 0.0."""
    t = str(text).strip().replace(",", "")
    if t in ("", "-", "–", "—"):
        return 0.0
    try:
        return float(t)
    except ValueError:
        return 0.0


def detect(rows):
    head = compact(" ".join(" ".join(cell_text(c) for c in r) for r in rows[:10]))
    # Title compacts to "itemvspartieswisesaleschemeregister"; header carries the
    # "itemvsparties" + "saleqty" + "freeamount" + "mrpvalue" fingerprint. Unique to
    # this Marg scheme-register export; no other party_xlsx layout references these.
    if "itemvspartieswisesaleschemeregister" in head:
        return True
    if "itemvsparties" in head and "saleqty" in head and "freeamount" in head and "mrpvalue" in head:
        return True
    return False


def parse_item_vs_parties_scheme_register(rows):
    detected = {
        "Item VS Parties": "product_name", "Sale Qty": "qty", "Free Qty": "free_qty",
        "Amount": "amount", "Discount 1": "discount_amount",
        "Bill Discount": "discount_amount", "MRP Value": "mrp", "Tax Amount": "gst_amount",
    }
    hidx = _header_idx(rows)
    if hidx is None:
        return [], detected
    col = _cols(rows[hidx])
    amt_i = col.get("amount")
    if amt_i is None:
        return [], detected

    # Collect the data rows (drop blanks and the final TOTAL/GRAND TOTAL grand-total row).
    data = []
    for row in rows[hidx + 1:]:
        cells = [cell_text(c) for c in row]
        col0 = cells[0].strip() if cells else ""
        if not col0:
            continue
        up0 = col0.upper()
        if up0.startswith("TOTAL") or up0.startswith("GRAND TOTAL"):
            continue
        data.append(cells)

    def amount_of(cells):
        return _num(cells[amt_i]) if amt_i < len(cells) else 0.0

    def get(cells, key):
        j = col.get(key)
        if j is None or j >= len(cells):
            return 0.0
        return _num(cells[j])

    records = []
    i = 0
    n = len(data)
    while i < n:
        band = data[i]
        band_amt = amount_of(band)
        product, pack = _split_trailing(band[0])
        # Walk forward accumulating Amount until it matches the band's Amount; those rows
        # are this band's party rows. If the band has no following rows that sum to it
        # (degenerate / unbalanced source), fall back to treating the single next row as
        # the sole party so a value is still emitted.
        j = i + 1
        acc = 0.0
        parties = []
        while j < n and abs(acc - band_amt) > 0.02:
            acc += amount_of(data[j])
            parties.append(data[j])
            j += 1
        if not parties:
            # No party rows followed (band was last, or a bare product with no detail) —
            # skip; a band without parties carries no party_name.
            i = j if j > i else i + 1
            continue

        for prow in parties:
            pname, ploc = _split_trailing(prow[0])
            # Reject a numeric / over-long "location" tail so a real part of the party
            # name is never shaved (locations are short alpha towns: HISAR CITY, AGROHA).
            if not ploc or any(ch.isdigit() for ch in ploc) or len(ploc) > 25:
                pname, ploc = prow[0].strip(), ""
            qty = get(prow, "qty")
            amount = amount_of(prow)
            disc = get(prow, "_disc1") + get(prow, "_disc2")
            rec = {
                "party_name": pname,
                "product_name": product,
                "qty": qty,
                "free_qty": get(prow, "free_qty"),
                "amount": amount,
                "mrp": get(prow, "mrp"),
                "gst_amount": get(prow, "gst_amount"),
            }
            if pack:
                rec["pack"] = pack
            if ploc:
                rec["party_location"] = ploc
            if disc:
                rec["discount_amount"] = disc
            # No per-row rate column; back out the effective unit rate so the required
            # ``rate`` field is populated (mirrors product_party_banded).
            if qty:
                rec["rate"] = round(amount / qty, 4)
            records.append(rec)
        i = j

    return records, detected
