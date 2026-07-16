"""
"Areawise Sales Statement" — BlueFox Systems bill-wise party export (TELY DRUGS / KLM,
one workbook per company/division: COSMO, COSMOCOR, DERMA, DERMACOR, PEDIA, PHARMA, COSMO-Q):

    TELY DRUGS
    PHARMACEUTICAL DISTRIBUTORS ...
    Areawise Sales Statement As On May-2026                    <- title (row 2)
    Company : KLM * ( COSMOCOR)                                <- company/division band (row 3)
    ... Bill No   Bill Date   Product Name   Packing   Qty   Free Qty   Amount   <- header (row 4)
    CHAKARAKKAL                                        1698.704   <- AREA band  (col 1 + subtotal)
      NEETHI MEDICAL STORE, IRIKKUR                    1698.704   <- PARTY band (col 2 + subtotal)
        9312  2026-05-15  NIOCLEAN AD GEL  15gm  5  0     782.054 <- sale line (col 3.. Amount last)
        9312  2026-05-15  NIOSOL OINT      30gm  6  0     916.65
    ...
    Grand Total :                                      933.72     <- footer (skip)
    Printed By : ... / Software @BlueFox ...                     <- footer (skip)

Three-level band: the AREA name sits alone in **column 1**, the PARTY name (indented) sits
alone in **column 2**, and each sale line starts at **column 3** (Bill No). The header cells are
spread across otherwise-empty columns, so ``detect_header_row``/``map_headers`` never binds a
party column and the file falls to generic ``tabular`` -> RED MISSING_REQUIRED_FIELD:party_name.

Because the header is scattered and the area/party bands are distinguished only by their column
index (1 vs 2), columns are mapped POSITIONALLY off the header row, not via core synonyms. The
sale-line Amount is the LAST populated cell (col 20; the header label "Amount" sits at col 21 and
the band SUBTOTAL amount at col 19 — neither is the sale figure). There is NO Rate column, so qty
and value stay independent and qty is NEVER derived from Amount.

MAPPING: division <- "Company :" band; party_location <- AREA band (col 1); party_name <- PARTY
band (col 2); invoice_number/invoice_date/product_name/pack/qty/free_qty <- fixed header columns;
amount <- last populated cell of the sale line.
"""
from core.header_match import normalize

from extractors.party_xlsx.parse_common import cell_text, compact

_TITLE = "areawisesalesstatement"
# The full header token run, present in NO other corpus file when paired with the title.
_HEADER_RUN = "billnobilldateproductnamepackingqtyfreeqtyamount"


def _header_idx(rows):
    """Row index of the scattered "Bill No .. Amount" header (within the first 12 rows)."""
    for i, row in enumerate(rows[:12]):
        run = compact(" ".join(cell_text(c) for c in row))
        if _HEADER_RUN in run:
            return i
    return None


def detect(rows):
    head = compact(" ".join(" ".join(cell_text(c) for c in r) for r in rows[:8]))
    return _TITLE in head and _header_idx(rows) is not None


def _positional_columns(header_row):
    """Map canonical field -> column index off the scattered header cells (positional)."""
    label_to_key = {
        "bill no": "invoice_number",
        "bill date": "invoice_date",
        "product name": "product_name",
        "packing": "pack",
        "qty": "qty",
        "free qty": "free_qty",
        "amount": "amount",
    }
    col = {}
    for idx, cell in enumerate(header_row):
        lab = normalize(cell_text(cell))
        key = label_to_key.get(lab)
        if key and key not in col:
            col[key] = idx
    return col


def _division_from_company_band(cell):
    """"Company : KLM * ( COSMOCOR)" -> "COSMOCOR" (the code inside the parens; strip stars)."""
    after = cell.split(":", 1)[1] if ":" in cell else cell
    if "(" in after and ")" in after:
        after = after[after.find("(") + 1: after.rfind(")")]
    return after.strip().strip("*").strip()


def parse_areawise_sales_statement(rows):
    detected = {"Bill No": "invoice_number", "Bill Date": "invoice_date",
                "Product Name": "product_name", "Packing": "pack", "Qty": "qty",
                "Free Qty": "free_qty", "Amount": "amount"}
    hidx = _header_idx(rows)
    if hidx is None:
        return [], detected
    col = _positional_columns(rows[hidx])
    bill_col = col.get("invoice_number")
    if bill_col is None:
        return [], detected

    # The "Company : KLM * ( COSMOCOR)" division band sits ABOVE the header (in the title
    # area) and holds the division code in parens. Seed it from the pre-header rows.
    division = ""
    for raw in rows[:hidx]:
        for c in raw:
            t = cell_text(c)
            if t.lower().startswith("company") and ":" in t:
                division = _division_from_company_band(t)
                break
        if division:
            break

    def at(cells, key):
        i = col.get(key)
        return cells[i].strip() if (i is not None and i < len(cells)) else ""

    records = []
    current_party = current_loc = ""
    for raw in rows[hidx + 1:]:
        cells = [cell_text(c) for c in raw]
        nonempty = [(i, c) for i, c in enumerate(cells) if c.strip()]
        if not nonempty:
            continue
        joined = " ".join(cells)
        low = joined.lower()

        # A "Company : KLM * ( COSMOCOR)" band may also recur mid-body (multi-company book);
        # refresh the division from whichever cell carries it.
        if nonempty[0][1].lower().startswith("company") and ":" in nonempty[0][1]:
            division = _division_from_company_band(nonempty[0][1])
            continue
        # Footer / totals — skip.
        if "grand total" in low or "sub total" in low or "subtotal" in low.replace(" ", ""):
            continue
        if low.strip().startswith("printed by") or "bluefox" in low or "page " in low:
            continue

        first_idx = nonempty[0][0]

        # Sale line: text begins at the Bill No column (col 3) — a bill number is present.
        bill = at(cells, "invoice_number")
        if first_idx >= bill_col and bill:
            product = at(cells, "product_name")
            qty = at(cells, "qty")
            if not product or not current_party:
                continue
            # Amount is the LAST populated cell of the line (never the header/subtotal column).
            amount = nonempty[-1][1]
            records.append({
                "division": division,
                "party_name": current_party,
                "party_location": current_loc,
                "product_name": product,
                "pack": at(cells, "pack"),
                "invoice_number": bill,
                "invoice_date": at(cells, "invoice_date"),
                "qty": qty.replace(",", ""),
                "free_qty": (at(cells, "free_qty") or "0").replace(",", ""),
                "amount": amount.replace(",", ""),
            })
            continue

        # AREA band: lone name in column 1 (subtotal amount ignored).
        if first_idx == 1:
            current_loc = cells[1].strip()
            continue
        # PARTY band: lone name in column 2 (subtotal amount ignored).
        if first_idx == 2:
            current_party = cells[2].strip()
            continue

    return records, detected
