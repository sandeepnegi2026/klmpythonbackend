"""RAPID MEDICO -- Marg "Normal Stock Statement" per-Company banded .xlsx export
(quantity-only movement grid; KLM LABORATORIES divisions COSMO Q / COSMO /
COSMOCORE / DERMA / DERMACORE / PED / PHARMA, one Company band each).

The report has a SPLIT two-row column header (the value columns are all blank on
this vendor -- only the leftmost quantity band and Expiry carry data). Collapsed &
lowercased, the two header rows read::

    row A: open recp othr    sales othr clsg  open recp   sales clsg <Open Stk> ...
    row B: sr. product name pack stk qty  total qty   stk                    expiry ...

Only the FIRST (leftmost) quantity band is populated per product row; the indices
are fixed across every Company band:

    col0 Sr.  col1 Product Name  col2 Pack
    col3 Open Stk   -> opening_stock  (opening qty)
    col4 Recp Qty   -> purchase_stock (receipt / inflow +)
    col5 Othr (Qty) -> other-receipt inflow (blank on this file; folded into +purchase)
    col6 Total      -> derived (opening+recp); NOT stored
    col7 Sales Qty  -> sales_qty       (outflow -)
    col8 Othr (Qty) -> other-issue outflow (blank on this file; folded into +sales_qty)
    col9 Clsg Stk   -> closing_stock   (closing qty)

With that mapping the stock identity
    closing = opening + purchase + purchase_free - purchase_return
              - sales_qty - sales_free + sales_return
holds on 100% of product rows (287/287 verified: col3+col4+col5-col7-col8 == col9).

This is a QUANTITY-ONLY report: every rupee/value column (cols 15..53:
<Open Stk>/<Purchase>/<Sales>/<Clsg Stk> value blocks, AvgSal, Prft. Approx.) is
empty on this vendor, so NO quantity is ever derived from a value column.

Why a dedicated parser: the generic ``tabular`` header mapper does not recognise the
split two-row header (the movement labels Open/Recp/Sales/Clsg live on one row while
Stk/Qty/Total live on the next) -> it finds no stock header and returns 0 rows.
This parser locks onto the two-row header by its exact token run, maps the quantity
band positionally, walks each Company band, and keeps ONLY rows whose col0 is a
serial number with a product name -- skipping the title/year/company bands and the
"Opening Rs / Sales Rs / Closing Rs / Rmks:" summary footer.
"""

from extractors.stock_xlsx.parse_common import cell_text, to_number


def _norm_row(row):
    return "".join(cell_text(c) for c in row).lower().replace(" ", "")


def _find_header(rows):
    """Return the index of the SECOND header row ('Sr. Product Name Pack Stk Qty ...')
    for the split two-row header, or None. The row above it must carry the movement
    labels 'open recp othr sales othr clsg'."""
    for idx in range(1, len(rows)):
        below = _norm_row(rows[idx])
        if "sr.productnamepackstkqtytotalqtystk" not in below:
            continue
        above = _norm_row(rows[idx - 1])
        if "openrecpothrsalesothrclsg" in above:
            return idx
    return None


def detect(rows):
    return _find_header(rows) is not None


def _num(row, i):
    if i >= len(row):
        return None
    return to_number(row[i])


def parse_marg_normal_ss_open_recp_othr_sales_clsg_qtyonly_xls(rows):
    hdr = _find_header(rows)
    if hdr is None:
        return [], {}

    records = []
    current_company = ""

    for row in rows[hdr + 1:]:
        first = cell_text(row[0]) if len(row) else ""
        low = first.lower()

        # Company band -> remember division; not a data row.
        if low.startswith("company"):
            div = first.split(":", 1)[1].strip() if ":" in first else ""
            current_company = div
            continue

        # Footer summary block (Opening Rs / Sales Rs / Closing Rs / Purchase Rs / Rmks).
        if low.startswith(("opening rs", "sales rs", "closing rs", "purchase rs", "rmks")):
            continue

        # Product rows always lead with a serial number in col0.
        if not first or not first.strip().isdigit():
            continue

        product = cell_text(row[1]) if len(row) > 1 else ""
        if not product:
            continue
        pack = cell_text(row[2]) if len(row) > 2 else ""

        opening = _num(row, 3)
        recp = _num(row, 4)
        othr_in = _num(row, 5)      # other receipt (inflow); blank on this vendor
        sales = _num(row, 7)
        othr_out = _num(row, 8)     # other issue (outflow); blank on this vendor
        closing = _num(row, 9)

        nums = [opening, recp, othr_in, sales, othr_out, closing]
        if all(x is None for x in nums):
            continue

        opening = opening or 0.0
        recp = recp or 0.0
        othr_in = othr_in or 0.0
        sales = sales or 0.0
        othr_out = othr_out or 0.0
        closing = closing or 0.0

        rec = {
            "product_name": product,
            "pack": pack,
            # Both receipt columns are pure inflows -> fold into purchase_stock.
            "opening_stock": opening,
            "purchase_stock": recp + othr_in,
            "purchase_free": 0.0,
            "purchase_return": 0.0,
            # Both issue columns are pure outflows -> fold into sales_qty.
            "sales_qty": sales + othr_out,
            "sales_free": 0.0,
            "sales_return": 0.0,
            "closing_stock": closing,
        }
        if current_company:
            rec["division"] = current_company

        records.append(rec)

    detected = {
        "Open Stk": "opening_stock",
        "Recp Qty": "purchase_stock",
        "Othr(recp) Qty": "purchase_stock (folded)",
        "Sales Qty": "sales_qty",
        "Othr(issue) Qty": "sales_qty (folded)",
        "Clsg Stk": "closing_stock",
    }
    return records, detected
