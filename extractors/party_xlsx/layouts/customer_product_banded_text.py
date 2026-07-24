"""
"Customer & Product Analysis" — single-column (fixed-width TEXT) banded party report.

SRI POORNA ENTERPRISES / KLM export (PADEATRIC.xlsx). The whole report lives in ONE
space-padded text cell per row of Sheet1 (ncols == 1): a glued header, "Customer :<name>"
band rows, dashed rules and per-customer / grand Total lines, plus the fixed-width detail
lines. It is the TEXT analogue of ``customer_product_banded`` (which reads real per-cell
columns) — same customer-band -> product-line semantics, but nothing is a separate cell,
so the figures are parsed off the fixed-width line, mirroring
``item_item_sales_summary_text``.

    _x001B_E ... Customer & Product  Analysis _x001B_F          <- title (OOXML-escaped)
    Inv.No   Date       Product          Pack   Batch   Qty Free Rate Value  <- glued header (col0)
    Customer :M/S CURE PHARMACY                                 <- customer band
    RI01360  14/05/2026 DESOSOFT CREAM 10 GR  1*10gr BJ511  5.00 0.00 107.15 535.75  <- detail
    Total:                                                 5.00 0.00 107.15 535.75  <- per-cust subtotal
    ...
    Grand Total :                                         46.00 15.00 773.82 7687.12 <- grand total

MAPPING (per detail line):
    invoice_number  <- Inv.No           party_name       <- carried "Customer :<name>" band
    invoice_date    <- Date (dd/mm/yyyy) product_name    <- Product (fixed-width, pack peeled)
    pack            <- Pack              batch_no         <- Batch
    qty <- Qty       free_qty <- Free    rate <- Rate      amount <- Value

RECONCILE: sum(qty) / sum(free_qty) / sum(amount) == printed "Grand Total" (qty / free /
Value). Dashed rules, "Total:", "Grand Total", "Page :" and the OOXML-escaped masthead are
skipped. Distinct from the columnar ``customer_product_banded`` because the whole
Inv.No..Value header sits in col0 ALONE (single-column signature).
"""
import re

from extractors.party_xlsx.parse_common import cell_text, compact

# The full header run lives in col0 alone as one glued string.
_HEADER_COMPACT = "invnodateproductpackbatchqtyfreeratevalue"
_TITLE_COMPACT = "customerproductanalysis"

# OOXML control-char escapes (_x000E_, _x001B_, _x0014_, ...) that leak into the text cells.
_OOXML_ESC_RE = re.compile(r"_x[0-9A-Fa-f]{4}_")

# "Customer :<name>" band (colon or dash after the keyword). Kept local so the reader is
# self-contained; the detector reuses the shared CUSTOMER_BAND_RE.
_CUSTOMER_RE = re.compile(r"^\s*customer\s*[:\-]\s*(.+)$", re.IGNORECASE)

# Detail line: Inv.No  dd/mm/yyyy  <product...>  <pack>  <batch>  qty free rate value.
# Product is greedy-lazy up to the fixed-width 2+-space gap before the pack; the trailing
# four numbers are the qty/free/rate/value columns.
_DATA_RE = re.compile(
    r"^(?P<inv>\S+)\s+"
    r"(?P<date>\d{2}/\d{2}/\d{4})\s+"
    r"(?P<prod>.*?)\s{2,}"
    r"(?P<pack>\S+)\s+"
    r"(?P<batch>\S+)\s+"
    r"(?P<qty>-?\d[\d,]*\.?\d*)\s+"
    r"(?P<free>-?\d[\d,]*\.?\d*)\s+"
    r"(?P<rate>-?\d[\d,]*\.?\d*)\s+"
    r"(?P<value>-?\d[\d,]*\.?\d*)\s*$"
)


def _clean(text):
    return _OOXML_ESC_RE.sub("", str(text)).replace("\xa0", " ")


def _is_dashes(text):
    s = text.strip()
    return bool(s) and set(s) <= set("-")


def _header_idx(rows):
    # col0 ALONE must carry the whole compacted header — the single-column signature.
    for i, row in enumerate(rows[:30]):
        if row and _HEADER_COMPACT in compact(_clean(cell_text(row[0]))):
            return i
    return None


def _num(tok):
    return tok.replace(",", "")


def detect(rows):
    hidx = _header_idx(rows)
    if hidx is None:
        return False
    head = compact(_clean(" ".join(cell_text(row[0]) for row in rows[:12] if row)))
    if _TITLE_COMPACT not in head:
        return False
    # Require at least one "Customer :" band so a columnar twin of the same header (which
    # would spread the tokens across real cells anyway) can never be claimed here.
    return any(
        _CUSTOMER_RE.match(_clean(cell_text(row[0])).strip())
        for row in rows[hidx + 1: hidx + 400]
        if row
    )


def parse_customer_product_banded_text(rows):
    detected = {
        "Inv.No": "invoice_number", "Date": "invoice_date", "Product": "product_name",
        "Pack": "pack", "Batch": "batch_no", "Qty": "qty", "Free": "free_qty",
        "Rate": "rate", "Value": "amount",
    }
    hidx = _header_idx(rows)
    if hidx is None:
        return [], detected

    records, party = [], ""
    for row in rows[hidx + 1:]:
        col0 = _clean(cell_text(row[0])).rstrip() if row else ""
        stripped = col0.strip()
        if not stripped or _is_dashes(stripped):
            continue

        band = _CUSTOMER_RE.match(stripped)
        if band:
            party = band.group(1).strip()
            continue

        low = stripped.lower()
        if low.startswith("total") or low.startswith("grand total") or low.startswith("page"):
            continue

        m = _DATA_RE.match(col0)
        if not m:
            continue
        rec = {
            "party_name": party,
            "product_name": m.group("prod").strip(),
            "pack": m.group("pack").strip(),
            "batch_no": m.group("batch").strip(),
            "qty": _num(m.group("qty")),
            "free_qty": _num(m.group("free")),
            "rate": _num(m.group("rate")),
            "amount": _num(m.group("value")),
            "invoice_number": m.group("inv").strip(),
            "invoice_date": m.group("date").strip(),
        }
        records.append(rec)

    return records, detected
