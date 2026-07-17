from extractors.stock_xlsx.parse_common import cell_text, to_number, is_subtotal


def _norm(value):
    return cell_text(value).lower().replace(".", "").replace(" ", "")


def _is_data_row(raw_row, product):
    """Same product-vs-band guard the fawin_stock sibling uses.

    A pure division band ("KLM COSMO", "KLM PEADIA", ...) carries only ONE
    non-empty cell, so it is dropped here; a genuine "KLM D3 NANO DROP 15ML"
    product row carries the full RATE/Stock/... number cells and survives, so
    we must NOT filter on a bare "KLM" prefix.
    """
    pl = product.lower().strip()
    non_empty_cells = [c for c in raw_row if str(c).strip()]
    return not (
        not product
        or len(non_empty_cells) <= 1
        or is_subtotal(product)
        or pl.startswith("company")
        or pl.startswith("division")
        or pl.startswith("items")
        or pl.endswith("division)")
    )


def parse_fawin_sales_fr_stock(rows):
    """Fawin "STOCK & SALES STATMENT" export — the SALES/FR. free-column variant
    (SUPRIYA MEDICAL AGENCY, one .xls per KLM division).

    This is the fawin_stock family, but its free-issue column is printed under a
    SECOND "SALES" group label with the sub-header "FR." (instead of the SWASTIK
    variant's dedicated "Free Sale"/"Qty" group). The generic fawin_stock parser
    only recognises the free column when its group normalises to "freesale", so on
    this export it DROPS the sales_free column entirely and closing under-reconciles
    by the free quantity on every discounted line. This parser resolves the field
    from the (group, sub) header pair exactly like fawin_stock but adds the
    "SALES"/"FR." -> sales_free branch, so closing reconciles as
    opening + purchase - purchase_return + sales_return - sales_qty - sales_free.

    Two-row header (idx -> group / sub):
      0  PRODUCT NAME & PACKING /              -> product_name
      3  / RATE                                (rate, ignored for the equation)
      4  Opeing / Stock                        -> opening_stock
      5  Purchase / QTY.                       -> purchase_stock
      6  Sales / Return                        -> sales_return
      7  L.M.S. / QTY                          (last-month sales, informational)
      8  Purc. / Retrun                        -> purchase_return
      9  SALES / QTY.                          -> sales_qty
     10  SALES / FR.                           -> sales_free   (the fix)
     11  Closing / QTY                         -> closing_stock
    """
    grp = sub = None
    for i, row in enumerate(rows[:8]):
        flat = " ".join(_norm(c) for c in row)
        if grp is None and "opeing" in flat and "closing" in flat:
            grp = i
        if sub is None and "productname" in flat:
            sub = i
    # Combined-header variant: "PRODUCT NAME & PACKING" shares the group band, so
    # grp == sub. The sub-labels ("Stock"/"QTY.") live on the NEXT row; promote sub
    # to that row so the (group, sub) resolver runs.
    if grp is not None and sub is not None and sub == grp and grp + 1 < len(rows):
        nxt = [_norm(c) for c in rows[grp + 1]]
        if "stock" in nxt and any("qty" in c for c in nxt):
            sub = grp + 1
    if grp is None or sub is None or grp == sub:
        return [], {}

    G = [_norm(c) for c in rows[grp]]
    S = [_norm(c) for c in rows[sub]]
    width = max(len(G), len(S))
    G += [""] * (width - len(G))
    S += [""] * (width - len(S))

    cmap = {}
    for i in range(width):
        g, s = G[i], S[i]
        if "productname" in s and "product_name" not in cmap:
            cmap["product_name"] = i
        elif g == "opeing" and "stock" in s and "opening_stock" not in cmap:
            cmap["opening_stock"] = i
        elif g == "purchase" and "qty" in s and "purchase_stock" not in cmap:
            cmap["purchase_stock"] = i
        elif g == "purc" and ("retrun" in s or "return" in s) and "purchase_return" not in cmap:
            cmap["purchase_return"] = i
        elif g == "sales" and "return" in s and "sales_return" not in cmap:
            cmap["sales_return"] = i
        elif g == "sales" and s == "fr" and "sales_free" not in cmap:
            cmap["sales_free"] = i
        elif g == "sales" and "qty" in s and "fr" not in s and "sales_qty" not in cmap:
            cmap["sales_qty"] = i
        elif g == "closing" and "qty" in s and "value" not in s and "closing_stock" not in cmap:
            cmap["closing_stock"] = i

    # Without a real opening+closing pair the resolution is untrustworthy.
    if "opening_stock" not in cmap or "closing_stock" not in cmap:
        return [], {}

    pidx = cmap.get("product_name", 0)
    start = max(grp, sub) + 1
    records = []
    for raw_row in rows[start:]:
        if not any(raw_row):
            continue
        # The export appends a "NEAR EXPIRY DATAILS FOR 6 MONTHS" batch annex after
        # the totals; everything past that marker has a different column shape.
        if cell_text(raw_row[0] if raw_row else "").strip().upper().startswith("NEAR EXPIRY"):
            break
        product = cell_text(raw_row[pidx]) if len(raw_row) > pidx else ""
        if not _is_data_row(raw_row, product):
            continue
        record = {"product_name": product}
        for field in ("opening_stock", "purchase_stock", "purchase_return",
                      "sales_qty", "sales_free", "sales_return", "closing_stock"):
            idx = cmap.get(field)
            if idx is not None and len(raw_row) > idx:
                record[field] = to_number(raw_row[idx])
        records.append(record)

    detected = {
        "Product Name & Packing": "product_name",
        "Opeing Stock": "opening_stock",
        "Purchase Qty.": "purchase_stock",
        "Sales Qty.": "sales_qty",
        "Sales Fr.": "sales_free",
        "Closing Qty": "closing_stock",
    }
    return records, detected
