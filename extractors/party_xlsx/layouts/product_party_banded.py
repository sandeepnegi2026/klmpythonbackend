"""
"Product + Party Wise List Report" — a product-banded party export (seen from AKSHAR
MEDICINES / KLM) whose columns are ``Product | Free | SaleQty. | ReturnQty | Amount``:

    Product + Party Wise List Report
    Product | Free | SaleQty. | ReturnQty | Amount
    KLM.COSMO*                                   <- division band (trailing '*')
    AASTHA MEDI & GEN STORE   VARACHHA           <- party band (name only, numbers blank)
    HERPIVAL 500 TAB 1*3 | 3 | 6 | 0 | 675       <- product line
    KLFLAM SP TAB        | 6 | 10 | 0 | 675
    Party Total:         | 12 | 22 | 0 | 2237.16 <- party subtotal (skip)
    ANA MEDICAL   ADAJAN                          <- next party band
    ...

The party name is a *band row* (column 0 only, every numeric column blank), not a
column, so the generic ``tabular`` parser maps Product/SaleQty/Amount correctly but
never attaches ``party_name`` (-> MISSING_REQUIRED_FIELD:party_name). This layout
carries the current party band down onto every product line until the next band, and
skips the division bands ('*') and ``Party Total:`` subtotals.
"""
import re

from core.header_match import normalize

from extractors.party_xlsx.parse_common import cell_text, is_subtotal

# Total/subtotal rows carry numbers (so they reach the product branch) but end in
# "...Total" / "...Total:" — e.g. "Party Total:", "Company Total:", "Mfg.Company Total:".
# ``is_subtotal`` only catches totals that *start* with "total", so match the suffix here.
_TOTAL_ROW_RE = re.compile(r"total\s*:?\s*$", re.IGNORECASE)

# Party bands carry the area glued onto the name three ways:
#   "AASTHA MEDI & GEN STORE   VARACHHA"      -> gap of 2+ spaces before the area
#   "DIVINE MEDICALS(KATARGAM)" / "... (AMROLI)" -> trailing parenthetical
#   "DR.VARSHA VIRANI - (MOTA VARACHHA)"      -> dash + parenthetical
# but a trailing "(DR. ...)" / "(...CLINIC)" is the doctor/clinic, NOT an area, so it
# must stay in the name (e.g. "SHIVAM CLINIC(DR.MAYUR VARIYA)").
_TRAILING_PAREN_RE = re.compile(r"[(\[]\s*([^()\[\]]+?)\s*[)\]]\s*$")
_NOT_AREA_RE = re.compile(r"(\bDR\.?\b|CLINIC|HOSPITAL|STUDIO|'S\b)", re.IGNORECASE)
_MULTISPACE_RE = re.compile(r"\s{2,}")


def _clean_area(area):
    area = area.strip().strip("-").strip()
    area = re.sub(r"^[\]\)\[(]+", "", area)
    area = re.sub(r"[\]\)\[(]+$", "", area)
    return _MULTISPACE_RE.sub(" ", area).strip()


def _clean_name(name):
    return _MULTISPACE_RE.sub(" ", name).strip().rstrip("-").strip()


def _split_name_location(text):
    """Split a band string into (party_name, party_location) for this vendor format.

    Prefers the 2+-space column gap (the vendor's own visual area column); falls back
    to a trailing parenthetical that is not a doctor/clinic. Always returns a non-empty
    name (whole string if no area is found) so party_name is never lost.
    """
    s = text.strip()
    runs = list(_MULTISPACE_RE.finditer(s))
    if runs:
        last = runs[-1]
        name, area = _clean_name(s[: last.start()]), _clean_area(s[last.end():])
        if name and area and len(area) <= 40 and re.search(r"[A-Za-z]", area):
            return name, area
        return _clean_name(s), ""
    match = _TRAILING_PAREN_RE.search(s)
    if match:
        inner = match.group(1).strip()
        if inner and len(inner) <= 40 and not _NOT_AREA_RE.search(inner):
            name = _clean_name(s[: match.start()])
            if name:
                return name, inner
    return _clean_name(s), ""


def _to_float(text):
    if text is None:
        return None
    m = re.search(r"-?\d[\d,]*\.?\d*", str(text))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def _header_idx(rows):
    """Row index of the ``Product | Free | SaleQty. | ReturnQty | Amount`` header."""
    for idx, row in enumerate(rows[:15]):
        toks = {normalize(cell_text(c)) for c in row if cell_text(c)}
        # Require the exact single-word cells Product + SaleQty + Amount together (the
        # AKSHAR/KLM "Product + Party Wise" fingerprint). Exact-cell (not substring)
        # tokens are what keep ordinary "Qty"/"Sale Qty"/"Item" headers from matching;
        # do not loosen to a contains-check.
        if "product" in toks and "saleqty" in toks and "amount" in toks:
            return idx
    return None


def _cols(header):
    """Map canonical keys -> column index from the header row's raw tokens."""
    col = {}
    for j, cell in enumerate(header):
        n = normalize(cell_text(cell))
        if n == "product" and "product_name" not in col:
            col["product_name"] = j
        elif n == "free":
            col["free_qty"] = j
        elif n == "saleqty":
            col["qty"] = j
        elif n == "returnqty":
            col["return_qty"] = j
        elif n == "amount":
            col["amount"] = j
    return col


def _numeric_cols_blank(cells, col):
    """True when the sale-qty AND amount columns are both empty (a band row).

    Product lines always carry a SaleQty/Amount figure (even '0'), so a row whose
    numeric columns are blank is a band header (party or division), not a product.
    """
    for key in ("qty", "amount"):
        i = col.get(key)
        if i is not None and i < len(cells) and cells[i].strip():
            return False
    return True


def detect(rows):
    header_idx = _header_idx(rows)
    if header_idx is None:
        return False
    col = _cols(rows[header_idx])
    if "product_name" not in col or "qty" not in col:
        return False
    # Require the band structure to actually be present (>=2 name-only party bands and
    # >=2 product lines) so a plain columnar file sharing these headers is not stolen.
    bands = prods = 0
    for raw in rows[header_idx + 1 : header_idx + 120]:
        cells = [cell_text(c) for c in raw]
        first = cells[0].strip() if cells else ""
        if not first:
            continue
        if _numeric_cols_blank(cells, col):
            if not first.endswith("*") and "total" not in first.lower():
                bands += 1
        else:
            prods += 1
    return bands >= 2 and prods >= 2


def parse_product_party_banded(rows):
    header_idx = _header_idx(rows)
    if header_idx is None:
        return [], {}
    col = _cols(rows[header_idx])

    def _val(cells, key):
        i = col.get(key)
        return cells[i] if (i is not None and i < len(cells)) else ""

    records = []
    current_party = ""
    current_loc = ""
    for raw in rows[header_idx + 1 :]:
        cells = [cell_text(c) for c in raw]
        first = cells[0].strip() if cells else ""
        if not first:
            continue

        if _numeric_cols_blank(cells, col):
            if first.endswith("*"):          # division band, e.g. "KLM.COSMO*"
                continue
            if "total" in first.lower() or is_subtotal(first):
                continue
            current_party, current_loc = _split_name_location(first)
            continue

        # product line
        if is_subtotal(first) or _TOTAL_ROW_RE.search(first):
            continue
        if not current_party:
            continue
        amount = _val(cells, "amount")
        qty = _val(cells, "qty")
        record = {
            "party_name": current_party,
            "product_name": first,
            "qty": qty,
            "free_qty": _val(cells, "free_qty"),
            "amount": amount,
            # This layout has no rate/price column; the "Amount" is the line net value.
            # Map it to the required taxable_value and back out the effective unit rate
            # (Amount / SaleQty) so the core numerics are populated.
            "taxable_value": amount,
        }
        amt_f, qty_f = _to_float(amount), _to_float(qty)
        if amt_f is not None and qty_f:
            record["rate"] = round(amt_f / qty_f, 4)
        if current_loc:
            record["party_location"] = current_loc
        ret = _val(cells, "return_qty")
        if ret:
            record["return_qty"] = ret
        records.append(record)

    detected = {"Product": "product_name", "Free": "free_qty", "SaleQty.": "qty",
                "ReturnQty": "return_qty", "Amount": "amount"}
    return records, detected
