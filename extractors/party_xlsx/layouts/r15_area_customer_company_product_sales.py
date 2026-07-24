"""
"Area Wise Customer, Company And Product Sales" — KLM/Marg XLSX party sales export
(PURUSHOTHAM MEDICAL AGENCIES, file "KLM.xlsx").

A two/three-level BANDED party sales report whose header maps too few columns for the
generic ``detect_header_row(min_matches=4)`` fallback, so it currently routes to
``unknown`` (0 rows, RED). Structure::

    PURUSHOTHAM MEDICAL AGENCIES                            <- firm block
    Area Wise Customer, Company And Product Sales           <- title
    From 01/06/2026 To 30/06/2026
    COMPANY :KLM(COSMO)                                     <- company/division band (col0)
    Name | Qty | Free | ComNet | Net                        <- header row
    Customer :1               | CITY:                       <- party band (col0=name, col1=CITY)
    IMXIA PLUS SHAMPOO | 1 |   | 308.47 | 3.08              <- product line
    ...
                     | Total:  1.00  308.47  3.08           <- per-party subtotal (skip)
    Customer :AJAY MEDICALS   | CITY:ANNAMAYYA DIST
    IMXIA F | 1 |   | 607.15 | 6.07
    ...
    Grand Total :  1720.00  203.00  264695.17  2646.95      <- grand total (skip)

COLUMN MAPPING (positional, bound by the exact header cells; qty/value kept SEPARATE,
never derived from each other):
    Name    (col0) -> product_name
    Qty     (col1) -> qty          (sale quantity; party-route canonical qty field)
    Free    (col2) -> free_qty     (scheme/free goods)
    ComNet  (col3) -> amount       (the net sale value; its Grand Total == 264695.17)
    Net     (col4) -> IGNORED      (a scaled figure == ComNet/100, not qty or a usable value)

The COMPANY band supplies ``division`` (e.g. "COMPANY :KLM(COSMO)" -> "KLM(COSMO)").
The party band is "Customer :<name>" in col0 with "CITY:<area>" in col1 -> party_name /
party_location.

This is a pure SALES report (no opening/purchase/closing columns), so the stock identity
does not apply; qty (Qty) and value (ComNet) are the only figures and are mapped from
their own separate columns. The per-party "Total:" and the final "Grand Total :" rows are
skipped.

GATE: the compact contiguous title token ``areawisecustomercompanyandproductsales``,
which no other corpus export carries.
"""
import re

from extractors.party_xlsx.parse_common import cell_text, compact, is_numeric_qty

_TITLE_TOKEN = "areawisecustomercompanyandproductsales"
_COMPANY_RE = re.compile(r"^\s*company\s*[:\-]\s*(.+)$", re.IGNORECASE)
_CUSTOMER_RE = re.compile(r"^\s*customer\s*[:\-]\s*(.+)$", re.IGNORECASE)
_CITY_RE = re.compile(r"^\s*city\s*[:\-]\s*(.*)$", re.IGNORECASE)


def _title_text(rows):
    return compact(" ".join(" ".join(cell_text(c) for c in r) for r in rows[:8]))


def _header_idx(rows):
    """Row index of the 'Name | Qty | Free | ComNet | Net' header."""
    for idx, row in enumerate(rows[:20]):
        norm = [compact(cell_text(c)) for c in row]
        if "name" in norm and "qty" in norm and "comnet" in norm:
            return idx
    return None


def detect(rows):
    if _TITLE_TOKEN not in _title_text(rows):
        return False
    return _header_idx(rows) is not None


def _is_total_row(cells):
    """True for a per-party 'Total:' or 'Grand Total' subtotal row (in any cell)."""
    for c in cells:
        t = cell_text(c).lower().lstrip()
        if t.startswith("total:") or t.startswith("total ") or "grand total" in t:
            return True
    return False


def parse_area_customer_company_product_sales(rows):
    header_idx = _header_idx(rows)
    if header_idx is None:
        return [], {}
    norm = [compact(cell_text(c)) for c in rows[header_idx]]

    def col(name):
        return norm.index(name) if name in norm else None

    name_i = col("name")
    qty_i = col("qty")
    free_i = col("free")
    amt_i = col("comnet")

    def at(cells, i):
        return cells[i].strip() if (i is not None and i < len(cells)) else ""

    # The "COMPANY :KLM(COSMO)" division band is printed ABOVE the header row (and may
    # repeat mid-report between product groups). Seed it from the pre-header rows so the
    # first party group is tagged, then keep updating it inside the main loop.
    division = ""
    for raw in rows[:header_idx]:
        for c in raw:
            m = _COMPANY_RE.match(cell_text(c).strip())
            if m:
                division = m.group(1).strip()

    records = []
    party = ""
    location = ""
    for raw in rows[header_idx + 1:]:
        cells = [cell_text(c) for c in raw]
        if not any(c.strip() for c in cells):
            continue
        first = cells[0].strip()

        m_comp = _COMPANY_RE.match(first)
        if m_comp:
            division = m_comp.group(1).strip()
            continue

        m_cust = _CUSTOMER_RE.match(first)
        if m_cust:
            party = m_cust.group(1).strip()
            location = ""
            # CITY sits in col1 (or any later cell) as "CITY:<area>".
            for c in cells[1:]:
                m_city = _CITY_RE.match(cell_text(c).strip())
                if m_city:
                    location = m_city.group(1).strip()
                    break
            continue

        if _is_total_row(cells):
            continue

        product = at(cells, name_i)
        qty = at(cells, qty_i)
        # A real product line carries a product name and a numeric qty. The repeated
        # header and the "Total:"/"Grand Total" furniture fail this.
        if not product or not is_numeric_qty(qty):
            continue
        if not party:
            continue

        records.append({
            "party_name": party,
            "party_location": location,
            "division": division,
            "product_name": product,
            "qty": qty,
            "free_qty": at(cells, free_i),
            "amount": at(cells, amt_i),
        })

    detected = {"Name": "product_name", "Qty": "qty", "Free": "free_qty",
                "ComNet": "amount", "Customer": "party_name", "CITY": "party_location",
                "COMPANY": "division"}
    return records, detected
