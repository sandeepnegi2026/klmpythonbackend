"""
Visual Infosoft batch-wise stock report.

Two-row header:
  Row 3 (categories): Opening | Purchase | Sales | Closing | Sales
  Row 4 (sub-headers): SrNo, ItemName, Batch, RefSrNo, ExpDt, Mrp,
                        P.Rate, LP, PTR, Inv.Rate,
                        Qty(10), MRP Value(11), ..., INV Value(15),   [Opening]
                        Qty(16), MRP Value(17), ..., INV Value(21),   [Purchase]
                        Qty(22), Free(23),                            [Sales]
                        Qty(24), MRP Value(25), ..., INV Value(29),   [Closing]
                        Value(30)                                     [Sales Value]

Data rows are batch-level (same product can appear multiple times).
We aggregate batches into a single product row.
"""
from collections import defaultdict

from extractors.stock_xlsx.parse_common import cell_text, is_subtotal, to_number


def parse_infosoft_stock(rows):
    """Parse Visual Infosoft batch-wise stock report."""
    # Find the header row that has 'SrNo' and 'ItemName'
    header_idx = None
    for idx in range(min(len(rows), 150)):
        cells = [cell_text(c).lower() for c in rows[idx]]
        if "srno" in cells and "itemname" in cells:
            header_idx = idx
            break
    if header_idx is None:
        return [], {}

    # Build column map from the header row
    header = [cell_text(c) for c in rows[header_idx]]
    col_map = {}
    for i, h in enumerate(header):
        col_map.setdefault(h, []).append(i)

    # Identify columns using category row (one row above header)
    # The category row tells us which 'Qty' is Opening vs Purchase vs Sales vs Closing
    cat_row = [cell_text(c).lower() for c in rows[header_idx - 1]] if header_idx > 0 else []

    # Map: find column indices by matching category + sub-header
    item_col = col_map.get("ItemName", [None])[0]
    batch_col = col_map.get("Batch", [None])[0]
    expiry_col = col_map.get("ExpDt", [None])[0]

    # Find Qty columns and classify by category
    qty_cols = col_map.get("Qty", [])
    opening_qty_col = None
    purchase_qty_col = None
    sales_qty_col = None
    closing_qty_col = None

    for qc in qty_cols:
        cat = cat_row[qc] if qc < len(cat_row) else ""
        if "opening" in cat:
            opening_qty_col = qc
        elif "purchase" in cat:
            purchase_qty_col = qc
        elif "sales" in cat:
            sales_qty_col = qc
        elif "closing" in cat:
            closing_qty_col = qc

    # Fallback: if categories not found, use positional order
    # (Opening, Purchase, Sales, Closing)
    if opening_qty_col is None and len(qty_cols) >= 4:
        opening_qty_col = qty_cols[0]
        purchase_qty_col = qty_cols[1]
        sales_qty_col = qty_cols[2]
        closing_qty_col = qty_cols[3]

    # Find 'Free' column for sales free
    free_cols = col_map.get("Free", [])
    sales_free_col = free_cols[0] if free_cols else None

    # Find closing value columns — last INV Value or Value column in closing section
    value_cols = col_map.get("INV Value", [])
    closing_value_col = None
    for vc in value_cols:
        cat = cat_row[vc] if vc < len(cat_row) else ""
        if "closing" in cat:
            closing_value_col = vc
    # Fallback: Sales Value column
    sales_value_col = col_map.get("Value", [None])[0]

    records = []
    for raw_row in rows[header_idx + 1:]:
        # Data rows start with a serial number
        srno = cell_text(raw_row[0]) if raw_row else ""
        if not srno or not srno.replace(".", "").isdigit():
            continue

        product = cell_text(raw_row[item_col]) if item_col is not None and item_col < len(raw_row) else ""
        if not product or is_subtotal(product):
            continue

        def _val(col):
            if col is None or col >= len(raw_row):
                return 0.0
            return to_number(raw_row[col]) or 0.0

        r = {
            "product_name": product,
            "opening_stock": _val(opening_qty_col),
            "purchase_stock": _val(purchase_qty_col),
            "sales_qty": _val(sales_qty_col),
            "closing_stock": _val(closing_qty_col),
        }

        # Batch
        batch = cell_text(raw_row[batch_col]) if batch_col is not None and batch_col < len(raw_row) else ""
        if batch:
            r["batch_no"] = batch

        # Expiry
        exp = cell_text(raw_row[expiry_col]) if expiry_col is not None and expiry_col < len(raw_row) else ""
        if exp:
            r["expiry"] = exp

        # MRP
        mrp_col = col_map.get("Mrp", [None])[0]
        if mrp_col is not None:
            r["mrp"] = _val(mrp_col)

        # Rate (PTR)
        rate_col = col_map.get("PTR", [None])[0]
        if rate_col is not None:
            r["rate"] = _val(rate_col)

        # Sales free
        if sales_free_col is not None:
            free_val = _val(sales_free_col)
            if free_val != 0.0:
                r["sales_free"] = free_val

        # Closing stock value
        if closing_value_col is not None:
            cl_val = _val(closing_value_col)
            if cl_val != 0.0:
                r["closing_stock_value"] = cl_val

        # Sales value
        if sales_value_col is not None:
            s_val = _val(sales_value_col)
            if s_val != 0.0:
                r["sales_value"] = s_val

        records.append(r)

    detected = {
        "ItemName": "product_name",
        "Opening Qty": "opening_stock",
        "Purchase Qty": "purchase_stock",
        "Sales Qty": "sales_qty",
        "Closing Qty": "closing_stock",
    }
    
    if batch_col is not None:
        detected[header[batch_col]] = "batch_no"
    if expiry_col is not None:
        detected[header[expiry_col]] = "expiry"
    mrp_col = col_map.get("Mrp", [None])[0]
    if mrp_col is not None:
        detected[header[mrp_col]] = "mrp"
    rate_col = col_map.get("PTR", [None])[0]
    if rate_col is not None:
        detected[header[rate_col]] = "rate"

    return records, detected
