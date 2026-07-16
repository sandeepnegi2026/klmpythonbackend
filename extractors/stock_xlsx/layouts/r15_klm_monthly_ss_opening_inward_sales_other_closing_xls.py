from extractors.stock_xlsx.parse_common import cell_text, is_subtotal, to_number


def _norm(value):
    return cell_text(value).lower().replace(" ", "")


def _find_header(rows):
    """Return (header_idx, col-map) for the first 'Product Name ... Opening ... Inward ...
    Sales ... Other ... Closing' band, or (None, {})."""
    for idx, row in enumerate(rows):
        flat = " ".join(cell_text(c) for c in row).lower().replace(" ", "")
        if (
            "productname" in flat
            and "packing" in flat
            and "opening" in flat
            and "inward" in flat
            and "sales" in flat
            and "other" in flat
            and "closing" in flat
        ):
            col = {}
            for i, cell in enumerate(row):
                key = _norm(cell)
                if key == "productname":
                    col["product"] = i
                elif key == "packing":
                    col["pack"] = i
                elif key == "opening":
                    col["opening"] = i
                elif key == "inward":
                    col["inward"] = i
                elif key == "sales":
                    col["sales"] = i
                elif key == "other":
                    col["other"] = i
                elif key == "closing":
                    col["closing"] = i
            if all(k in col for k in ("product", "opening", "inward", "sales", "other", "closing")):
                return idx, col
    return None, {}


def detect(rows):
    idx, _ = _find_header(rows)
    return idx is not None


_SKIP_PREFIXES = (
    "product name",
    "total values",
    "purchase bills",
    "pending debit",
    "list of products",
    "outstanding summary",
    "total outstanding",
    "company",
    "division",
    "year :",
    "monthly sales",
    "* e stands",
    "grand total",
    "page ",
)


def parse_klm_monthly_ss_opening_inward_sales_other_closing_xls(rows):
    """KLM "Monthly Sales and Stock Statement" per-division banded .xls export
    (PARAS DISTRIBUTORS -- Company: KLM - KLM LAB; one Division band per page:
    PHARMA / DERMA / COSMO / PEDIATRIC / COSMOQ / DERMACOR / COSMOCOR).

    The report is a Crystal-style ``.rpt.xls`` with values scattered across sparse,
    fixed spreadsheet columns. A single repeated header band (once per division page)
    carries the EXACT tokens, and the column INDICES stay constant across bands::

        Product Name (col0) | Packing (col10) | Opening (col14) | Inward (col17) |
        Sales (col19) | Other (col22) | Closing (col24)

    Movement -> canonical mapping (mapped by exact header text -> its column index):
        Opening -> opening_stock   (opening qty)
        Inward  -> purchase_stock  (inflow +; the report's only purchase column)
        Sales   -> sales_qty       (outflow -)
        Other   -> signed adjustment: positive folds into +sales_return, negative
                   folds into -purchase_return (e.g. KLM FX 120 TAB Other=-4)
        Closing -> closing_stock   (closing qty)

    With that mapping the stock identity
        closing = opening + purchase + purchase_free - purchase_return
                  - sales_qty - sales_free + sales_return
    holds on 100% of product rows (verified across all 93 product rows / 7 divisions).

    Why a dedicated parser: the generic ``tabular`` header mapper mishandles this sparse,
    multi-band, per-division layout -- it does not bind the "Inward" inflow column into a
    purchase slot nor fold the signed "Other" adjustment, so its closing reconcile fails on
    the affected rows. This parser walks the sheet band-by-band (resetting the current
    division on each ``Division :`` marker), keeps ONLY rows that carry a product name, a
    pack, and at least one numeric stock cell, and skips every section footer/listing
    (Total Values / Purchase Bills / List of Products WithOut Stock / Outstanding Summary /
    Pending Debit Note's), which otherwise leak product-like text as phantom rows.

    NEVER derives a quantity from a value column: the "Total Values is based on PRate" band
    (rupee totals in the same columns) is skipped, and no rupee value is read as a qty.
    """
    header_idx, base_col = _find_header(rows)
    if header_idx is None:
        return [], {}

    def val(row, key):
        i = base_col.get(key)
        if i is None or i >= len(row):
            return None
        return to_number(row[i])

    records = []
    current_division = ""
    in_band = False  # True only between a header band and its "Total Values" footer.

    for row in rows:
        first = cell_text(row[0]) if len(row) else ""
        low = first.lower()

        # Track the current division band (header appears just below it).
        if low.startswith("division"):
            div = ""
            for cell in row[1:]:
                t = cell_text(cell)
                if t and t != ":":
                    div = t
                    break
            current_division = div
            continue

        # Detect the product header row -> open the product band.
        flat = " ".join(cell_text(c) for c in row).lower().replace(" ", "")
        if "productname" in flat and "opening" in flat and "closing" in flat and "inward" in flat:
            in_band = True
            continue

        # The "Total Values is based on PRate" footer closes the band. Everything after it
        # (Purchase Bills, Pending Debit Note's, List of Products WithOut Stock, Outstanding
        # Summary) is NOT product data and is ignored until the next header.
        if low.startswith("total values"):
            in_band = False
            continue

        if not in_band:
            continue
        if not first:
            continue
        if any(low.startswith(p) for p in _SKIP_PREFIXES):
            continue
        if is_subtotal(first):
            continue

        pack = ""
        pi = base_col.get("pack")
        if pi is not None and pi < len(row):
            pack = cell_text(row[pi])

        opening = val(row, "opening")
        inward = val(row, "inward")
        sales = val(row, "sales")
        other = val(row, "other")
        closing = val(row, "closing")

        nums = [opening, inward, sales, other, closing]
        # Must carry at least one real numeric movement cell (not None/blank).
        if all(x is None for x in nums):
            continue
        # A product row inside the band always has a pack; skip stray text otherwise.
        if not pack:
            continue

        opening = opening or 0.0
        inward = inward or 0.0
        sales = sales or 0.0
        other = other or 0.0
        closing = closing or 0.0

        rec = {
            "product_name": first,
            "pack": pack,
            "opening_stock": opening,
            "purchase_stock": inward,
            "purchase_free": 0.0,
            "purchase_return": 0.0,
            "sales_qty": sales,
            "sales_free": 0.0,
            "sales_return": 0.0,
            "closing_stock": closing,
        }
        # Signed "Other" adjustment: + adds to closing (fold into +sales_return),
        # - subtracts from closing (fold into -purchase_return).
        if other > 0:
            rec["sales_return"] = other
        elif other < 0:
            rec["purchase_return"] = -other

        if current_division:
            rec["division"] = current_division

        records.append(rec)

    detected = {
        "Product Name": "product_name",
        "Packing": "pack",
        "Opening": "opening_stock",
        "Inward": "purchase_stock",
        "Sales": "sales_qty",
        "Other": "sales_return/purchase_return (signed)",
        "Closing": "closing_stock",
    }
    return records, detected
