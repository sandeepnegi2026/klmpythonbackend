"""KLM "STOCK & SALES ANALYSIS" reduced 5-cell GRID with a dual-number CLOSING cell
(KUSHAL DISTRIBUTORS, "STKEX.xlsx").

Single-row header, five physical columns:

    ITEM DESCRIPTION | OPENING | RECEIPT | ISSUE | CLOSING

Unlike the AMETOMBI single-column TEXT dump (``stock_sales_analysis_oic_xlsx`` — every
row is ONE fixed-width cell and the header carries a trailing ``M.EXP``), this KUSHAL
export keeps OPENING / RECEIPT / ISSUE each in their own physical cell, but the CLOSING
cell holds TWO space-glued numbers::

    ITEM DESCRIPTION        OPENING  RECEIPT  ISSUE   CLOSING
    CETALORE TAB  10*10      167      300      274    193   123
    EBERFINE XL CREAM 50G    100       60       86     74   119

The first CLOSING number is the closing QUANTITY and the second is the closing VALUE
(rupees). Mapping (verified: closing_qty = opening + receipt - issue on 185/185 rows,
e.g. CETALORE TAB 167 + 300 - 274 = 193):

    OPENING            -> opening_stock
    RECEIPT            -> purchase_stock          (receipt inflow, +)
    ISSUE              -> sales_qty               (issue outflow, -)
    CLOSING token[0]   -> closing_stock           (closing quantity)
    CLOSING token[1]   -> closing_stock_value     (closing value, outside the qty identity)

Why a dedicated parser: the generic ``tabular`` reader treats the whole ``193   123``
CLOSING cell as one non-numeric token, so ``closing_stock`` reads 0 on EVERY row and the
book fails the stock identity (SANITY_FAILED on 98% of rows) even though the SOURCE numbers
reconcile exactly. The single-column ``stock_sales_analysis_oic_xlsx`` sibling would join
the five cells and grab the LAST four numeric tokens, which slides the CLOSING value into
the movement window and shifts every column left by one (it reads O=300/R=274/I=193/C=123
for the CETALORE row) — wrong. This positional 5-cell parser splits the CLOSING cell and
takes only its first token as the quantity, so the identity holds.

'-' means nil (0). The report is division-banded (bare "KLM LAB PVT LTD (PHARMA)" title
rows where columns 1..4 are all empty) with "TOTAL <value totals>" subtotals — bands carry
no movement numbers (dropped) and TOTAL rows are removed by ``is_subtotal``. A stray packing
token (a bare count, an "N*M" strip, or an "N-M" band) glued to the end of the description
is peeled into ``pack`` so the product name stays clean.

Gate token (compact contiguous header run, unique to this grid): the five adjacent header
cells collapse to ``itemdescriptionopeningreceiptissueclosing``. Gated with ``not
single_col`` and the ABSENCE of ``m.exp``/``dump``/``purchases``/``reorder`` — every other
OPENING/RECEIPT/ISSUE/CLOSING sibling is either single-column or carries one of those tokens,
so this steals none of them.
"""
import re

from extractors.stock_xlsx.parse_common import cell_text, is_subtotal, to_number

# The five header cells, normalized (lower, stripped). CLOSING may render as "closing" only.
_HEADER_SEQUENCE = ["item description", "opening", "receipt", "issue", "closing"]

# A stray packing-column token stuck on the end of the description: a bare count ("10"),
# an "N*M" strip ("1*10", "10*10"), or an "N-M" band ("1-10"). Unit-suffixed tokens
# ("60ML", "30GM") are genuine name descriptors and are left for the pipeline pack extractor.
_PACK_RE = re.compile(r"^\d+(?:[*\-x]\d+)?$")


def _norm(cell):
    return re.sub(r"\s+", " ", cell_text(cell).strip().lower())


def _find_header(rows):
    """Return the index of the ITEM DESCRIPTION..CLOSING header row, or None."""
    for idx in range(min(len(rows), 30)):
        cells = [_norm(c) for c in rows[idx]]
        head = [c for c in cells if c]
        if head[: len(_HEADER_SEQUENCE)] == _HEADER_SEQUENCE:
            return idx
    return None


def detect(rows):
    populated = [row for row in rows if any(cell_text(c) for c in row)]
    single_col = bool(populated) and all(
        sum(1 for c in row if cell_text(c)) <= 1 for row in populated
    )
    if single_col:
        return False
    flat = " ".join(
        " ".join(cell_text(c) for c in row) for row in rows[:30]
    ).lower().replace(" ", "")
    return (
        "itemdescriptionopeningreceiptissueclosing" in flat
        and "m.exp" not in flat
        and "mexp" not in flat
        and "dump" not in flat
        and "purchases" not in flat
        and "reorder" not in flat
        and _find_header(rows) is not None
    )


def _num_or_nil(token):
    token = token.strip()
    if token in {"", "-", "-----"}:
        return "0"
    val = to_number(token)
    return str(int(val)) if (val is not None and float(val).is_integer()) else (
        str(val) if val is not None else "0"
    )


def parse_klm_ss_analysis_oic_dualclose_grid_xls(rows):
    hdr = _find_header(rows)
    if hdr is None:
        return [], {}

    records = []
    for raw_row in rows[hdr + 1:]:
        cells = [cell_text(c) for c in raw_row]
        if len(cells) < 5:
            continue
        product = cells[0].strip()
        if not product or is_subtotal(product):
            continue
        opening, receipt, issue, closing = (
            cells[1].strip(),
            cells[2].strip(),
            cells[3].strip(),
            cells[4].strip(),
        )
        # A division band title row: only the description cell is filled, no movement.
        if not any((opening, receipt, issue, closing)):
            continue
        # The CLOSING cell carries "<closing_qty> <closing_value>". Take the FIRST token as
        # the quantity; the second (if any) is the closing value — never a quantity.
        close_tokens = closing.split()
        closing_qty = close_tokens[0] if close_tokens else ""
        closing_val = close_tokens[1] if len(close_tokens) > 1 else ""

        # Peel a trailing packing token (bare count / N*M / N-M) off the description.
        name_parts = product.split()
        pack = ""
        if len(name_parts) >= 2 and _PACK_RE.match(name_parts[-1]):
            pack = name_parts.pop()
        name = " ".join(name_parts).strip()
        if not name:
            continue

        record = {
            "product_name": name,
            "opening_stock": _num_or_nil(opening),
            "purchase_stock": _num_or_nil(receipt),
            "sales_qty": _num_or_nil(issue),
            "closing_stock": _num_or_nil(closing_qty),
            "closing_stock_value": _num_or_nil(closing_val),
        }
        if pack:
            record["pack"] = pack
        records.append(record)

    detected = {
        "ITEM DESCRIPTION": "product_name",
        "OPENING": "opening_stock",
        "RECEIPT": "purchase_stock",
        "ISSUE": "sales_qty",
        "CLOSING (qty)": "closing_stock",
        "CLOSING (value)": "closing_stock_value",
    }
    return records, detected
