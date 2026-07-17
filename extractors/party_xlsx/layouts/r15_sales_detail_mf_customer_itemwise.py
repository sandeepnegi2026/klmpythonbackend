"""KLM "Sales Detail Register (Mf-Customer-Itemwise)" — Marg/KLM XLSX export
(MARUTI MEDICAL AGENCY ``KLM BATCHWISE 05-26.XLSX``).

A batchwise SALES (party) register, banded Manufacturer -> Customer -> Item, whose
data cells live at fixed, WIDELY-SPACED column indices (the export pads dozens of empty
columns), so the generic ``tabular`` / header-mapped readers find no usable header row
and yield 0 rows (``marg_register_excel`` claims it and extracts nothing -> RED).

Layout (values sit at fixed columns; header row 4):

    Item(1) .......... Batch(39) . Qty(45) S.Qty(46) . S.Rate(48) . MRP(50) . Amount(52)
    MF : M00062 - KLM LAB COSMO [ COSMO ]                        <- manufacturer band (col1 "MF :")
    1. Invoice ............... 20 ....... 4 ............... 5080.23  <- invoice subtotal (skip)
    PUSHPAM DRUG HOUSE, AHMEDABAD .. -(42) ............... 3732.08   <- CUSTOMER band (col42 == "-")
    EKRAN AQUA GEL 50GM  AA3601  10  2  277.97  410  2696.31         <- item sale line (has Batch)
    ......
                        270 ...... 54 .............. 5080.23         <- MF grand total (col1 blank; skip)

Row classification (col1 = "first", plus the Batch column):
    * MF band          : first starts with "MF :"   -> set division ("KLM LAB COSMO")
    * invoice subtotal : first matches "<n>. Invoice" -> skip
    * customer band    : first non-empty, col42 == "-", Batch cell empty -> set party (name, town)
    * item line        : Batch cell non-empty -> emit a record
    * grand total      : first blank (only the numeric subtotal columns filled) -> skip

MAPPING (exact header text -> canonical; qty and value kept SEPARATE, never derived):
    Item    -> product_name
    Batch   -> batch_no
    Qty     -> qty          (primary sale quantity; the billed column)
    S. Qty  -> free_qty     (secondary / scheme quantity; NOT billed -> free)
    S. Rate -> rate
    MRP     -> mrp
    Amount  -> amount

RECONCILE (this file): each item line's Amount == Qty * S.Rate minus a small line
discount (row 7: 10 * 277.97 = 2779.70, Amount 2696.31; the footer states
"Amount = Q x R - Disc"); the billed column is Qty, NOT Qty + S.Qty. Every CUSTOMER
band's Amount equals the running Amount-sum of its item lines, and the per-MF
"n. Invoice" subtotal equals the sum of its customer bands (COSMO: 3732.08 + 1348.15 =
5080.23 = "1. Invoice"). S.Qty is a scheme quantity (~1/5 of Qty) that is not billed.

GATE: the compact title run ``salesdetailregistermfcustomeritemwise`` (the full report
title with parens/hyphens normalized away). It is a long, contiguous, report-specific
header run, so it can only ever claim this export and never steals a GREEN file.
"""
import re

from extractors.party_xlsx.parse_common import cell_text, compact

_GATE = "salesdetailregistermfcustomeritemwise"

# col1 band prefixes.
_MF_RE = re.compile(r"^\s*MF\s*:", re.IGNORECASE)
# "1. Invoice", "2. Invoice" ... subtotal introducer.
_INVOICE_RE = re.compile(r"^\s*\d+\s*\.\s*invoice\b", re.IGNORECASE)
# "MF : M00062 - KLM LAB COSMO [ COSMO ]" -> strip code and trailing "[ short ]".
_MF_CLEAN_RE = re.compile(r"^\s*MF\s*:\s*[A-Z0-9]+\s*-\s*", re.IGNORECASE)
_BRACKET_TAIL_RE = re.compile(r"\s*\[[^\]]*\]\s*$")


def _header_idx(rows):
    for i, row in enumerate(rows[:12]):
        if _GATE in compact(" ".join(cell_text(c) for c in row)):
            return i
    return None


def detect(rows):
    return _header_idx(rows) is not None


def _num(tok):
    tok = (tok or "").strip().replace(",", "")
    if not tok or tok == "-":
        return "0"
    return tok


def _clean_division(text):
    raw = _MF_CLEAN_RE.sub("", text.strip())
    raw = _BRACKET_TAIL_RE.sub("", raw)
    return " ".join(raw.split())


def _split_party(text):
    """"NAME, TOWN" customer band -> (trade name, town)."""
    raw = " ".join(text.split())
    if "," in raw:
        name, town = raw.split(",", 1)
        return name.strip(), town.strip()
    return raw.strip(), ""


def parse_sales_detail_mf_customer_itemwise(rows):
    detected = {
        "Item": "product_name",
        "Batch": "batch_no",
        "Qty": "qty",
        "S. Qty": "free_qty",
        "S. Rate": "rate",
        "MRP": "mrp",
        "Amount": "amount",
    }

    # Locate the title/gate line, then find the real column-header row just below it
    # ("Item ... Batch ... Qty ... Amount") and bind columns by their exact header text.
    gate_idx = _header_idx(rows)
    if gate_idx is None:
        return [], detected

    col = {}
    header_idx = None
    for i in range(gate_idx, min(gate_idx + 6, len(rows))):
        cells = [cell_text(c) for c in rows[i]]
        low = [c.strip().lower() for c in cells]
        if "item" in low and "amount" in low and "batch" in low:
            for j, c in enumerate(cells):
                key = c.strip().lower()
                if key == "item":
                    col.setdefault("item", j)
                elif key == "batch":
                    col.setdefault("batch", j)
                elif key == "qty":
                    col.setdefault("qty", j)
                elif key in ("s. qty", "s.qty", "sqty"):
                    col.setdefault("sqty", j)
                elif key in ("s. rate", "s.rate", "srate"):
                    col.setdefault("rate", j)
                elif key == "mrp":
                    col.setdefault("mrp", j)
                elif key == "amount":
                    col.setdefault("amount", j)
            header_idx = i
            break
    if header_idx is None or "item" not in col or "batch" not in col:
        return [], detected

    ic, bc = col["item"], col["batch"]

    def at(cells, key):
        j = col.get(key)
        return cells[j].strip() if (j is not None and j < len(cells)) else ""

    records = []
    current_div = current_party = current_loc = ""
    for raw in rows[header_idx + 1:]:
        cells = [cell_text(c) for c in raw]
        if not any(c.strip() for c in cells):
            continue
        first = cells[ic].strip() if ic < len(cells) else ""
        batch = cells[bc].strip() if bc < len(cells) else ""

        # ---- item line: the Batch column is populated ------------------------
        # Merged-cell replication guard: xlsx_io fills a merged range with its
        # text, and on CUSTOMER-band rows the party name's merge span (cols
        # 1..41 in the MARUTI .XLSX) covers the Batch column, so cells[bc]
        # equals the replicated Item-cell text instead of being empty -- every
        # band row then mis-classified as an item line, current_party never
        # set, 0 rows. A real item line's Batch cell always holds its OWN
        # value (the Item merge stops before the Batch column), so only treat
        # the row as an item line when the Batch text differs from the Item
        # text. On non-replicated sources (.XLS via xlrd) band rows have an
        # empty Batch cell and item rows have batch != first, so this guard
        # changes nothing there.
        if batch and batch != first:
            item = first
            if not item or not current_party:
                continue
            records.append(
                {
                    "division": current_div,
                    "party_name": current_party,
                    "party_location": current_loc,
                    "product_name": item,
                    "batch_no": batch,
                    "qty": _num(at(cells, "qty")),
                    "free_qty": _num(at(cells, "sqty")),
                    "rate": _num(at(cells, "rate")),
                    "mrp": _num(at(cells, "mrp")),
                    "amount": _num(at(cells, "amount")),
                }
            )
            continue

        # ---- band / subtotal rows (no Batch) ---------------------------------
        if not first:
            # grand-total row (only the padded numeric columns filled) -> skip
            continue
        if _MF_RE.match(first):
            current_div = _clean_division(first)
            current_party = current_loc = ""
            continue
        if _INVOICE_RE.match(first):        # "n. Invoice" subtotal introducer
            continue
        # anything else with text in the Item column and no batch is a CUSTOMER band
        current_party, current_loc = _split_party(first)

    return records, detected
