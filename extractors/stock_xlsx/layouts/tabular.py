import re

from core.header_match import map_headers, map_headers_indexed

from extractors.stock_xlsx.parse_common import cell_text, is_subtotal

# dd/mm/yyyy or dd-mm-yy etc. — a stock QUANTITY cell is never a date.
_DATE_RE = re.compile(r"^\s*\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\s*$")
# canonical fields that are always pure quantities (a date here ⇒ not a stock row)
_QTY_FIELDS = ("opening_stock", "closing_stock", "sales_qty", "purchase_stock")
# Marg "STOCK & SALE STATEMENT" grand-total FOOTER lines printed under the grid, where the
# whole label+value lands in the product column with every quantity column zero, e.g.
# "OPENING :   73755.58", "PURCHASE :   43553.69", "SALES :   35306.18", "UC SALE :  11904.97",
# "CL.STK.:   80910.39", "Opening/Purchase/Closing On SaleRate: ...", "MR.Balance:  0.00". A real
# product name is never a bare movement keyword immediately followed by a colon, so this signature
# (keyword, optional " On SaleRate", optional trailing dots, then ':') is unique to these rows.
_STOCK_TOTALS_FOOTER_RE = re.compile(
    r"^(opening|purchase|sale|sales|uc\s*sale|cl\.?\s*stk|closing|mr\.?\s*balance)"
    r"(\s+on\s+sale\s*rate)?[.\s]*:",
    re.I,
)


def _is_section_header(raw_row):
    """Detect section/division header rows (e.g. 'COMPANY : KLM LABS (COS)').

    When Excel has merged cells spanning all columns, pandas unmerges them
    and fills every column with the same value.  We detect this by checking
    if all non-empty cells contain the identical text.
    """
    non_empty = [cell_text(c) for c in raw_row if cell_text(c)]
    if not non_empty:
        return False
    # All cells identical → merged section header
    if len(set(non_empty)) == 1:
        return True
    return False


def records_from_rows(rows, header_idx):
    headers = [cell or f"col_{idx}" for idx, cell in enumerate(rows[header_idx])]
    # headers_detected keeps its existing (text-keyed) shape for the header-scan phase…
    header_map = map_headers(headers, "stock")
    detected = {raw: info["canonical"] for raw, info in header_map.items()}
    # …but build the rows by COLUMN INDEX so a header text repeated across merged columns
    # (e.g. 5x "ITEM DESCRIPTION") can no longer clobber product_name and drop every row.
    by_index = map_headers_indexed(headers, "stock")
    # the product-column header text ("ITEM DESCRIPTION"), so page-break repeats of the
    # column header — which map every quantity cell to a label and come out all-zero —
    # can be recognised and skipped.
    prod_idx = next((i for i, k in by_index.items() if k == "product_name"), None)
    header_product = (
        cell_text(rows[header_idx][prod_idx]).strip().lower()
        if prod_idx is not None and prod_idx < len(rows[header_idx])
        else ""
    )
    records = []
    for raw_row in rows[header_idx + 1 :]:
        if not any(raw_row):
            continue
        record = {}
        for idx, key in by_index.items():
            if idx < len(raw_row):
                record[key] = raw_row[idx]
        product = cell_text(record.get("product_name"))
        if not product or is_subtotal(product):
            continue
        # Skip division/section header rows — only 1 non-empty cell in the raw row
        non_empty = sum(1 for c in raw_row if cell_text(c))
        if non_empty <= 1:
            continue
        # Skip merged-cell section headers (all cells identical)
        if _is_section_header(raw_row):
            continue
        # Skip rows where product starts with known section markers.
        # "total"/"itemname"/"productname" cover glued footers/headers that the
        # word-boundary-anchored SUBTOTAL_RE misses: e.g. the per-company footer
        # "TotalKLM(DERMACOR)" (no space after "Total") and a batch-expiry
        # sub-report header "Itemname Batch Expiry Qty ..." reprinted below the
        # stock table (its quantity cells map to labels and come out all-zero).
        pl = product.lower().strip()
        if pl.startswith("company") or pl.startswith("division") or pl.startswith("manufacturer") or pl.startswith("values") or pl.startswith("total") or pl.startswith("item name") or pl.startswith("itemname") or pl.startswith("product name") or pl.startswith("productname") or pl.startswith("supplier") or pl.startswith("purchase invoice") or pl.startswith("sale invoice") or pl.startswith("sr.no") or pl.startswith("s.no"):
            continue
        # Skip Marg grand-total footer lines ("OPENING : 73755.58", "CL.STK.: 80910.39",
        # "Closing On SaleRate: 94044.7") that print the whole label+value in the product cell.
        if _STOCK_TOTALS_FOOTER_RE.match(pl):
            continue
        # Skip a pure separator / rule line (product name is only dashes/underscores/
        # asterisks/punctuation, e.g. the "--------------------" divider printed under an
        # appended purchase-invoice register) — a real product always has a letter or digit.
        if pl and not any(ch.isalnum() for ch in pl):
            continue
        # Skip a column-header row reprinted at a page break (product cell == the
        # detected header's product-column text, e.g. repeated "ITEM DESCRIPTION").
        if header_product and pl == header_product:
            continue
        # Skip total rows where product name is just a number
        if pl.replace(".", "", 1).isdigit():
            continue
        # Skip rows from an appended bill/purchase register stacked under the stock table:
        # those carry an invoice DATE in a quantity column (a real stock qty is never a date).
        if any(_DATE_RE.match(cell_text(record.get(f))) for f in _QTY_FIELDS):
            continue
        records.append(record)
    return records, detected

