"""KLM/Marg "Areawise Partywise Sales Summary" (Gujarat/PALANPUR parties).

This XLSX export nests **party band -> product lines**, the reverse of the PDF
``product_party_wise_list`` (which nests division/company -> party -> products).
The unusual twist is that sale **quantity/free are not printed in dedicated columns** —
they are encoded only in a parenthetical ``(saleQty+freeQty)`` sub-row printed
*immediately below* each product line. The visible value columns ("May" and "Total")
both carry the same rupee **amount**.

Row shapes (17 cells wide for data rows, 1 cell for a party band):

* Report furniture:  vendor/address (row 0), ``Year : ...`` / ``Page`` (row 1),
  the title ``Areawise Partywise Sales Summary`` + ``Period : ...`` (row 2),
  ``Area   :`` / ``All`` (row 3), the column header
  ``Product Name | Pack | Make | May | Total`` (row 4).
* Party band:  a lone cell ``CODE - PARTY NAME, CITY`` in column 0
  (e.g. ``A071 - ABC MEDICINES, PALANPUR``).
* Product line:  ``name(0) ... Pack(3) Make(4) ... May-value(6) ... Total-value(16)``.
* Paren sub-line:  ``(qty+free)`` at columns 6 and 16 (all other cells blank).
* ``Total of <CODE> :`` per-party subtotal (+ its own ``(sumQty+sumFree)`` line).
* ``Grand Total : 999948 999948`` (a VALUE total) and ``Notes :`` / ``ADMIN`` footer.

Parsing pairs each product line with the *next* ``(N+M)`` sub-row to recover
qty/free, reads the amount from the Total column, and carries the current party
(name = firm before the comma, location = city after it).
"""
import re

from extractors.party_xlsx.parse_common import cell_text, compact

try:  # split_gujarat_party_area lives in the party_pdf sibling; fall back to comma-split.
    from extractors.party_pdf.party_area import split_gujarat_party_area
except Exception:  # pragma: no cover - defensive
    split_gujarat_party_area = None

# Compact title token that uniquely marks this export (matches detect.py gate).
_TITLE_SIGNAL = "areawisepartywisesalessummary"

# Party band cell: "CODE - PARTY NAME, CITY" (code is short alnum, a dash, then a
# firm name, then a comma + city). The comma tail is what tells it apart from a
# product line, which has no leading "<code> - ".
_BAND_RE = re.compile(r"^[A-Z0-9][A-Z0-9./]{0,9}\s*-\s*.+,\s*.+$")
# Per-party / grand subtotal label ("Total of A071 :", "Grand Total :").
_TOTAL_RE = re.compile(r"^\s*(total of\b|grand\s*total\b)", re.IGNORECASE)
# The (qty+free) sub-line, e.g. "(25+5)".
_PAREN_RE = re.compile(r"^\(\s*(\d+)\s*\+\s*(\d+)\s*\)$")

# Column indices (fixed across every data row in this export).
_PACK_COL = 3
_MAKE_COL = 4
_MAY_COL = 6
_TOTAL_COL = 16


def title_matches(rows):
    head = compact(" ".join(" ".join(cell_text(c) for c in r) for r in rows[:8]))
    return _TITLE_SIGNAL in head


def _split_party(band_text):
    # Strip the leading "CODE - " so only "PARTY NAME, CITY" remains.
    body = re.sub(r"^[A-Z0-9][A-Z0-9./]{0,9}\s*-\s*", "", band_text).strip()
    # This export always prints "<firm>, <city>" — the city sits after the LAST comma
    # (some firm names carry their own commas). Comma-split is authoritative here; the
    # Gujarat-town splitter only helps the rare comma-less band.
    if "," in body:
        parts = [p.strip() for p in body.split(",")]
        name = ", ".join(parts[:-1]).strip()
        return name, parts[-1]
    if split_gujarat_party_area is not None:
        name, area = split_gujarat_party_area(body)
        if name:
            return name, area
    return body, ""


def _num(text):
    text = cell_text(text).replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _paren_of(rows, i):
    """Return (qty, free) from the (N+M) sub-row that follows product row ``i``.

    The paren sits in the value columns (6/16); scan the immediate next non-empty
    row's cells for the first "(n+m)" token.
    """
    for row in rows[i + 1: i + 3]:
        if not row:
            continue
        for cell in row:
            m = _PAREN_RE.match(cell_text(cell))
            if m:
                return float(m.group(1)), float(m.group(2))
        # a non-blank, non-paren row means the sub-line is absent for this product
        if any(cell_text(c) for c in row):
            return None, None
    return None, None


def _is_paren_row(row):
    for cell in row:
        if _PAREN_RE.match(cell_text(cell)):
            return True
    return False


def parse_areawise_partywise_summary_xlsx(rows):
    records = []
    current_name = current_area = ""
    detected = {
        "Product Name": "product_name",
        "Pack": "pack",
        "May": "amount",
        "Total": "amount",
        "(qty+free)": "qty/free_qty",
    }

    for i, row in enumerate(rows):
        if not row:
            continue
        first = cell_text(row[0])
        if not first:
            # a pure paren row (already consumed by its product) or blank spacer
            continue

        # party band: a lone "CODE - NAME, CITY" cell (rest of the row is blank).
        rest_blank = all(not cell_text(c) for c in row[1:])
        if rest_blank and _BAND_RE.match(first) and not _TOTAL_RE.match(first):
            current_name, current_area = _split_party(first)
            continue

        # subtotal / grand-total lines and their paren sub-lines: skip.
        if _TOTAL_RE.match(first):
            continue
        if _is_paren_row(row):
            continue

        # a product line must carry a value; qty/free come from the next paren row.
        amount = _num(row[_TOTAL_COL] if _TOTAL_COL < len(row) else "")
        if amount is None:
            amount = _num(row[_MAY_COL] if _MAY_COL < len(row) else "")
        if amount is None:
            continue
        if not current_name:
            continue

        qty, free = _paren_of(rows, i)
        pack = cell_text(row[_PACK_COL]) if _PACK_COL < len(row) else ""

        record = {
            "party_name": current_name,
            "party_location": current_area,
            "product_name": first,
            "pack": pack,
            "amount": amount,
        }
        if qty is not None:
            record["qty"] = qty
        if free is not None:
            record["free_qty"] = free
        records.append(record)

    return records, detected
