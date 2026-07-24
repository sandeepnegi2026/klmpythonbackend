"""S.M. MEDICAL ENTERPRISE converter "STOCK & SALES ANALYSIS" (sale+value / closing+value).

A dot-matrix "STOCK & SALES ANALYSIS" report exported to .xlsx as one report PAGINATED
across many "Table N" sheets (28 for S.M.). Each product row is:

    ITEM DESCRIPTION [split across 1-4 cells] | <pack> | SALE-QTY | SALE-VALUE | CLOSING-QTY | CLOSING-VALUE

Zero-movement products still print, negatives appear for returns/adjustments, and the item
name is split across a variable number of cells (dot-matrix column wobble). The four numeric
columns are ALWAYS the last four numeric cells of the row; the pack is the last non-numeric
cell before them; the item name is everything before the pack.

Because the report is paginated, the pipeline concatenates ALL sheets into one row list
before calling this parser (see pipeline.extract's _SM_SSA gate) — load_data_sheets' per-tab
scoring would otherwise drop continuation pages (S.M.: keeps 19/28 -> 97 of 312 rows).

Column -> canonical:  SALE-QTY -> sales_qty,  SALE-VALUE -> sales_value,
                      CLOSING-QTY -> closing_stock,  CLOSING-VALUE -> closing_stock_value.
There is NO opening/purchase in the grid, so the postprocess stock-identity sanity is
inapplicable (it will warn per row — expected). Completeness is proven instead by the printed
grand "TOTAL" line, which reconciles EXACTLY: sum(sales_qty/value) & sum(closing qty/value)
== 5088 / 850934 / 4962 / 828424 across 312 rows.

Division bands are the "KLM <DIV>" heading rows (no numeric cells); supplier "PURCHASE DETAIL"
rows carry a yyyy-mm-dd date cell and are skipped.
"""
import re

_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_NUM_RE = re.compile(r"^-?\d+(?:\.\d+)?$")
# first-cell prefixes that mark non-product rows (totals, page furniture, section heads)
_SKIP_FIRST = (
    "total", "purchase", "supplier", "s.m", "stock &", "item description",
    "continued", "<===", "page no",
)


def _num(cell):
    s = cell.strip().replace(",", "")
    return float(s) if _NUM_RE.match(s) else None


def _clean_division(cells):
    text = " ".join(c for c in cells if c.strip())
    # "KLM LABORATORIES PVT.LTD(COSMO)" / "KLM COSMOQ" / "KLM ORTHO" -> COSMO / COSMOQ / ORTHO
    m = re.search(r"\(([^)]*)", text)
    if m and m.group(1).strip():
        return m.group(1).strip()
    toks = [t for t in text.split() if t.upper() not in
            ("KLM", "LABORATORIES", "LABORATORY", "LABORTORIS", "LABORTORI",
             "LABORTARISE", "LABORATORIS", "PVT", "PVT.LTD", "LTD", "PVT.LTD.", "(")]
    return " ".join(toks).strip() or text.strip()


def parse_sm_stock_sales_analysis(rows):
    records = []
    division = ""
    for row in rows:
        cells = [c for c in row if c.strip()]
        if not cells:
            continue
        if any(_DATE_RE.search(c) for c in cells):   # PURCHASE DETAIL supplier rows
            continue
        first = cells[0].strip().lower()
        if first.startswith(_SKIP_FIRST):
            continue

        # indices of numeric cells within the compacted row
        nums = [(i, _num(c)) for i, c in enumerate(cells)]
        nums = [(i, v) for i, v in nums if v is not None]
        if len(nums) < 4:
            # a "KLM <DIV>" band heading (no numbers) sets the current division;
            # anything else with < 4 numbers is dropped.
            if first.startswith("klm"):
                division = _clean_division(cells)
            continue

        (sq_i, sq), (sv_i, sv), (cq_i, cq), (cv_i, cv) = nums[-4:]
        prefix = cells[:sq_i]                       # item + pack, before the 4 value cells
        pack = ""
        for j in range(len(prefix) - 1, -1, -1):
            if _num(prefix[j]) is None:             # last non-numeric cell = pack
                pack = prefix[j]
                name_cells = prefix[:j] + prefix[j + 1:]
                break
        else:
            name_cells = prefix
        name = " ".join(name_cells).strip()
        if not name:
            continue

        records.append({
            "product_name": name,
            "pack": pack,
            "division": division,
            "sales_qty": sq,
            "sales_value": sv,
            "closing_stock": cq,
            "closing_stock_value": cv,
        })
    return records, {"layout": "sm_stock_sales_analysis"}
