"""
"Customer & Product Analysis" — SPLIT-CELL, Batch-trailing variant (PADMALAYA MEDICAL
AGENCIES / KLM export, PEDIA__REPORT.txt.xlsx).

This is a second-generation twin of ``customer_product_banded_text``. Both are the same
single-column fixed-width "Customer & Product  Analysis" report, but they differ in TWO
structural ways that make one parser unable to read the other:

  1) HEADER PLACEMENT
     ``customer_product_banded_text`` carries the WHOLE header glued into col0 alone:
         col0 = "Inv.No   Date   Product   Pack   Batch   Qty Free Rate Value"
     THIS variant splits the header across real cells AND across two physical rows:
         row A: [Inv.No] [Date] [] [Product] [] [Pack] ... [Batch]
         row B: [Qty   Free] [Rate] [] [Value]
     so col0 of the header row compacts to just "invno" (never the full run), and the
     older layout's ``_header_idx`` (which needs the full run in col0) returns None ->
     the file falls through to generic ``tabular`` -> MISSING_REQUIRED_FIELD:party_name.

  2) COLUMN ORDER ON THE DETAIL LINE
     ``customer_product_banded_text`` reads  Product Pack *Batch* Qty Free Rate Value.
     THIS variant emits                       Product Pack Qty Free Rate Value *Batch*
     (Qty/Free come BEFORE Rate/Value and the Batch number is LAST), so the older
     ``_DATA_RE`` cannot match a line here even after re-gluing.

LAYOUT of a detail record (may be on one grid row, or split over two):
    <InvNo> <dd/mm/yyyy> <Product...> <Pack> <Qty> <Free>          <- "head"
                                     <Rate> <Value> <Batch>        <- "value" (next row)
When the product is short enough it is all on ONE row:
    <InvNo> <dd/mm/yyyy> <Product...> <Pack> <Qty> <Free> <Rate> <Value> <Batch>

MAPPING:
    invoice_number <- Inv.No          party_name  <- carried "Customer :<name>" band
    invoice_date   <- Date            product_name<- Product (fixed-width, pack peeled)
    pack           <- Pack            batch_no    <- Batch (LAST token)
    qty <- Qty      free_qty <- Free  rate <- Rate  amount <- Value
RECONCILE (sales): amount == qty * rate on each detail line (holds on ~all lines).

A minority of grid rows are damaged by the xlsx export (a value line and the following
head line are interleaved via embedded newlines within one cell, sometimes gluing two
records together). Those rows are skipped rather than guessed, so no scrambled record is
ever emitted; the clean rows still cover the bulk of the report.

GATE TOKEN: the compacted header run ``invnodateproductpackbatch`` PLUS the
``customerproductanalysis`` title, WITH col0 of that header row compacting to just
``invno`` (the split-cell signature that separates it from the col0-glued twin).
"""
import re

from extractors.party_xlsx.parse_common import cell_text, compact

_HEADER_A_COMPACT = "invnodateproductpackbatch"     # header row A, cells joined
_TITLE_COMPACT = "customerproductanalysis"

# "Customer :<name>  Add :<area>" band. Colon or dash after each keyword.
_CUSTOMER_RE = re.compile(
    r"^\s*customer\s*[:\-]\s*(?P<party>.+?)(?:\s+add(?:ress)?\s*[:\-]\s*(?P<area>.+))?$",
    re.IGNORECASE,
)

# Line starts "<InvNo> <dd/mm/yyyy> ...". Inv codes here are 2 letters + 4+ digits (GG05414).
_INVDATE_RE = re.compile(r"^([A-Z]{2}\d{4,})\s+(\d{2}/\d{2}/\d{4})\s+(.*)$")

# Whole detail on one line: PROD ... Qty Free Rate Value [Batch]
_FULL_TAIL_RE = re.compile(
    r"^(?P<prod>.+?)\s+"
    r"(?P<qty>-?\d[\d,]*\.?\d*)\s+"
    r"(?P<free>-?\d[\d,]*\.?\d*)\s+"
    r"(?P<rate>-?\d[\d,]*\.?\d*)\s+"
    r"(?P<value>-?\d[\d,]*\.?\d*)"
    r"(?:\s+(?P<batch>\S+))?\s*$"
)
# Head-only line (product wrapped): PROD ... Qty Free   (ends after two numbers)
_HEAD_TAIL_RE = re.compile(
    r"^(?P<prod>.+?)\s+(?P<qty>-?\d[\d,]*\.?\d*)\s+(?P<free>-?\d[\d,]*\.?\d*)\s*$"
)
# Value line following a wrapped head: Rate Value Batch
_VALUE_RE = re.compile(
    r"^(?P<rate>-?\d[\d,]*\.?\d*)\s+(?P<value>-?\d[\d,]*\.?\d*)\s+(?P<batch>[A-Z0-9][A-Z0-9\-]*)\s*$"
)
# A pure per-customer / grand subtotal figure line: four numbers, nothing else.
_SUBTOTAL_NUMS_RE = re.compile(
    r"^-?\d[\d,]*\.?\d*\s+-?\d[\d,]*\.?\d*\s+-?\d[\d,]*\.?\d*\s+-?\d[\d,]*\.?\d*\s*$"
)
_INV_ANCHOR_RE = re.compile(r"[A-Z]{2}\d{4,}\s+\d{2}/\d{2}/\d{4}")


def _dedupe(seq):
    out = []
    for c in seq:
        if out and out[-1] == c:
            continue
        out.append(c)
    return out


def _row_text(row):
    """Collapse a grid row to one logical string (replicated cells de-duped)."""
    cells = _dedupe([cell_text(c) for c in row if cell_text(c)])
    return " ".join(cells).strip()


def _is_corrupt(row):
    """Rows the xlsx export interleaved: embedded newline in any cell, or col0 holding
    two invoice anchors (two records glued). These cannot be de-interleaved reliably."""
    if any("\n" in str(c) for c in row):
        return True
    c0 = str(row[0]) if row else ""
    return len(_INV_ANCHOR_RE.findall(c0)) >= 2


def _peel_pack(prod):
    toks = prod.split()
    pack = ""
    if len(toks) >= 2 and re.search(r"\d", toks[-1]):
        pack = toks[-1]
        toks = toks[:-1]
    return " ".join(toks).strip(), pack


def _num(tok):
    return tok.replace(",", "")


def _header_row_idx(rows):
    """Row whose cells joined+compacted carry the full 'invnodateproductpackbatch' run
    while col0 ALONE compacts to just 'invno' (the split-cell signature).

    The real export REPLICATES each header cell across its merged columns
    ('Inv.No','Date','Date','Product','Product','Pack'x15,'Batch'x7), so the cells
    must be consecutive-de-duped (same as _row_text already does for data rows)
    before the join — un-deduped the compacted run reads 'invnodatedateproduct...'
    and the token never matches, detect() returns False, and the file falls through
    to generic tabular -> MISSING_REQUIRED_FIELD:party_name (RED)."""
    for i, row in enumerate(rows[:30]):
        if not row:
            continue
        cells = _dedupe([cell_text(c) for c in row if cell_text(c)])
        joined = compact(" ".join(cells))
        if _HEADER_A_COMPACT in joined and compact(cell_text(row[0])) != joined:
            return i
    return None


def detect(rows):
    hidx = _header_row_idx(rows)
    if hidx is None:
        return False
    title = compact(" ".join(cell_text(r[0]) for r in rows[: hidx + 2] if r))
    if _TITLE_COMPACT not in title:
        return False
    # At least one "Customer :" band below the header.
    for row in rows[hidx + 1: hidx + 400]:
        if row and _CUSTOMER_RE.match(_row_text(row)):
            return True
    return False


def parse_r15_customer_product_analysis_split_batchtail(rows):
    detected = {
        "Inv.No": "invoice_number", "Date": "invoice_date", "Product": "product_name",
        "Pack": "pack", "Batch": "batch_no", "Qty": "qty", "Free": "free_qty",
        "Rate": "rate", "Value": "amount",
    }
    hidx = _header_row_idx(rows)
    if hidx is None:
        return [], detected

    records = []
    party = ""
    area = ""
    pending = None  # wrapped head awaiting its value line

    for row in rows[hidx + 1:]:
        if not row:
            continue
        if _is_corrupt(row):
            pending = None
            continue
        s = _row_text(row)
        if not s:
            continue
        low = s.lower()
        if (
            "analysis" in low
            or low.startswith("from ")
            or low.startswith("inv.no")
            or low.startswith("qty")
            or low.startswith("page")
            or set(s) <= set("-")
        ):
            continue

        band = _CUSTOMER_RE.match(s)
        if band:
            party = band.group("party").strip()
            area = (band.group("area") or "").strip()
            pending = None
            continue

        if low.startswith("total") or low.startswith("grand"):
            pending = None
            continue

        md = _INVDATE_RE.match(s)
        if md:
            inv, date, rest = md.group(1), md.group(2), md.group(3)
            mf = _FULL_TAIL_RE.match(rest)
            if mf and re.search("[A-Za-z]", mf.group("prod")):
                prod, pack = _peel_pack(mf.group("prod").strip())
                records.append({
                    "party_name": party, "party_location": area,
                    "invoice_number": inv, "invoice_date": date,
                    "product_name": prod, "pack": pack,
                    "qty": _num(mf.group("qty")), "free_qty": _num(mf.group("free")),
                    "rate": _num(mf.group("rate")), "amount": _num(mf.group("value")),
                    "batch_no": (mf.group("batch") or "").strip(),
                })
                pending = None
                continue
            mh = _HEAD_TAIL_RE.match(rest)
            if mh and re.search("[A-Za-z]", mh.group("prod")):
                prod, pack = _peel_pack(mh.group("prod").strip())
                pending = {
                    "party_name": party, "party_location": area,
                    "invoice_number": inv, "invoice_date": date,
                    "product_name": prod, "pack": pack,
                    "qty": _num(mh.group("qty")), "free_qty": _num(mh.group("free")),
                }
                continue
            pending = None
            continue

        mv = _VALUE_RE.match(s)
        if mv and pending is not None:
            pending["rate"] = _num(mv.group("rate"))
            pending["amount"] = _num(mv.group("value"))
            pending["batch_no"] = mv.group("batch").strip()
            records.append(pending)
            pending = None
            continue

        if _SUBTOTAL_NUMS_RE.match(s):
            pending = None
            continue

    return records, detected
