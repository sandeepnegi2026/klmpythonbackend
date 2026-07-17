"""Saleable Stock Report — pipe-delimited Q+F movement (SURANA DRUG DISTRIBUTORS).

Text PDF. One product per line, split cleanly on '|' into fixed cells:

    Particular | Packing |   | Opn | Rec | Issue | Bal
       cell0      cell1   c2  cell3  cell4  cell5   cell6

Rows are grouped under "COMPANY : <division>" bands; each band closes with a
"COMPANY Total" quantity line immediately followed by a value line
"| |A| <opening_val>| <rec_val>| <issue_val>| <bal_val>"; the report ends with a
"Firm Total" grand-total pair. Columns are quantity+free combined (Q+F). Nil is
printed as an em-dash which the text layer renders as a broken glyph (e.g. "��").

Movement semantics are identical to simple4:
    opening = Opn, purchase = Rec, sales = Issue, closing = Bal
and reconcile exactly (opening + receipt - issue == closing on every sampled row;
Firm Total 1792 + 4065 - 4058 == 1799).

We parse by pipe-cell splitting (not shared whitespace tokenizing) so KLM-named
products (KLM D3 60K CAP, KLM FX 180) are retained — the shared _skip_line KLM
prefix drop is never invoked here. Nil glyphs are converted to 0.0 locally so the
shared _to_number / NUM_RE are untouched.
"""
import re

# Nil is an em-dash the text layer mangles into replacement / dash glyphs.
_NIL = {"", "-", "--", "—", "――", "──", "—", "―"}
_NUM_RE = re.compile(r"^-?\d[\d,]*\.?\d*$")

# Labels that must never be treated as a product name.
_TOTAL_LABEL_RE = re.compile(
    r"^(company\s*total|firm\s*total|grand\s*total|total|particular|packing|\(q\s*\+\s*f\))",
    re.I,
)


def _to_num(cell):
    """Convert a pipe cell to a float; em-dash / dash / blank nil -> 0.0.

    Returns None if the cell is present but not numeric-or-nil (so a malformed
    row is rejected rather than silently zeroed)."""
    t = cell.strip()
    # Strip any leftover mangled em-dash glyph runs (replacement char etc.).
    stripped = t.replace("�", "").replace("—", "").replace("―", "")
    stripped = stripped.replace("-", "").replace("—", "").replace("―", "").strip()
    if stripped == "":
        return 0.0
    if _NUM_RE.match(t.replace(" ", "")):
        try:
            return float(t.replace(",", "").rstrip("."))
        except ValueError:
            return None
    return None


def _is_pack(cell):
    """A packing cell is simply non-empty (e.g. 50GM, 10'S, PC, or a bare '10').

    Total / band / value lines all leave this cell empty, and the header row
    ("Packing") is rejected upstream by _TOTAL_LABEL_RE, so a non-empty test is
    enough to admit real products — including bare-number packs like 'GLUTADERM
    PLUS TAB |10' that a unit-suffix check would wrongly drop."""
    return bool(cell.strip())


def parse_saleable_stock_qf(text, file_bytes=None):
    records = []
    for raw in text.splitlines():
        line = raw.rstrip("\n")
        if "|" not in line:
            continue
        cells = [c.strip() for c in line.split("|")]
        if len(cells) < 7:
            continue

        name = cells[0].strip()
        pack = cells[1].strip()

        # Value line "| |A| ...": empty name, marker in cell[2] -> skip.
        # Band header / total / sub-header lines -> skip.
        if not name:
            continue
        if _TOTAL_LABEL_RE.match(name):
            continue
        if name.lower().startswith("company"):  # "COMPANY : <div>" band
            continue
        if not _is_pack(pack):
            continue

        # Trailing four cells: Opn, Rec, Issue, Bal (right-most four).
        opn = _to_num(cells[-4])
        rec = _to_num(cells[-3])
        iss = _to_num(cells[-2])
        bal = _to_num(cells[-1])
        if None in (opn, rec, iss, bal):
            continue
        if opn == 0 and rec == 0 and iss == 0 and bal == 0:
            continue

        records.append(
            {
                "product_name": name,
                "pack": pack,
                "opening_stock": opn,
                "purchase_stock": rec,
                "sales_qty": iss,
                "closing_stock": bal,
            }
        )
    return records
