"""RAJA ENTERPRISE converter "STOCK & SALES ANALYSIS" — Opening/Receipt/Issue/Closing variant.

Same paginated converter as [[sm_stock_sales_analysis]] (one report across many "Table N"
sheets), but this vendor's book prints the QUANTITY movement columns instead of the
sale+value pair. Each product row is:

    ITEM DESCRIPTION [split cells, pack may be glued] | <pack> | OPENING | RECEIPT | ISSUE | CLOSING

The four trailing numeric cells are OPENING, RECEIPT, ISSUE, CLOSING (all quantities).
Map: OPENING -> opening_stock, RECEIPT -> purchase_stock (inflow), ISSUE -> sales_qty
(outflow), CLOSING -> closing_stock. The postprocess stock identity then holds exactly
(closing = opening + purchase - sales), which is THE reconcile oracle here — the printed
"TOTAL" rows are running VALUE subtotals (rupees), not per-row-summable quantities, so
completeness is proven by the per-row identity holding on every row instead.

Pipeline concatenates all sheets before calling this (see pipeline.extract's SSA gate);
supplier "SUPPLIER NAME / INVOICE / DATE / AMOUNT" rows carry yyyy-mm-dd dates and are
skipped, division bands are the "KLM LABORATORIES (DIV)" headings.
"""
import re

_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_NUM_RE = re.compile(r"^-?\d+(?:\.\d+)?$")
_PACK_TAIL = re.compile(r"(.*?)\s+(\d+\s*\*\s*\d+|\d+\s*(?:GR|GM|ML|MG|'?S|TAB|CAP|BOX|PC|KG|LTR|L)\b.*)$", re.I)
_SKIP_FIRST = (
    "total", "supplier", "raja", "stock &", "item description", "continued",
    "page no", "grand total", "opening",
)


def _num(cell):
    s = cell.strip().replace(",", "")
    return float(s) if _NUM_RE.match(s) else None


def _clean_division(cells):
    text = " ".join(c for c in cells if c.strip())
    m = re.search(r"\(([^)]*)", text)
    if m and m.group(1).strip():
        return m.group(1).strip().rstrip(")")
    toks = [t for t in text.split() if t.upper() not in
            ("KLM", "LABORATORIES", "LABORATORY", "PVT", "PVT.LTD", "LTD", "(")]
    return " ".join(toks).strip() or text.strip()


def parse_raja_stock_oric_analysis(rows):
    records = []
    division = ""
    for row in rows:
        cells = [c for c in row if c.strip()]
        if not cells:
            continue
        if any(_DATE_RE.search(c) for c in cells):   # supplier detail rows
            continue
        first = cells[0].strip().lower()
        if first.startswith(_SKIP_FIRST):
            continue

        nums = [(i, _num(c)) for i, c in enumerate(cells)]
        nums = [(i, v) for i, v in nums if v is not None]
        if len(nums) < 4:
            if first.startswith("klm"):
                division = _clean_division(cells)
            continue

        (op_i, op), (rc_i, rc), (is_i, iss), (cl_i, cl) = nums[-4:]
        prefix = cells[:op_i]
        pack = ""
        name_cells = prefix
        for j in range(len(prefix) - 1, -1, -1):
            if _num(prefix[j]) is None:
                cell = prefix[j].strip()
                m = _PACK_TAIL.match(cell)   # pack often GLUED to item ("GLUTADERM TAB   1*10")
                if m:
                    name_cells = prefix[:j] + [m.group(1)] + prefix[j + 1:]
                    pack = m.group(2).strip()
                else:
                    pack = cell
                    name_cells = prefix[:j] + prefix[j + 1:]
                break
        name = " ".join(name_cells).strip()
        if not name:
            continue

        records.append({
            "product_name": name,
            "pack": pack,
            "division": division,
            "opening_stock": op,
            "purchase_stock": rc,
            "sales_qty": iss,
            "closing_stock": cl,
        })
    return records, {"layout": "raja_stock_oric_analysis"}
