from extractors.stock_xlsx.parse_common import cell_text, to_number, is_subtotal


def _norm(value):
    return cell_text(value).lower().replace(".", "").replace(" ", "")


def _is_data_row(raw_row, product):
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


def _legacy_fixed_index(rows):
    """Original Fawin parser: fixed column indices (opening=4, purchase=5, sales=9,
    closing=11). Kept as the fallback for any future export whose two-row header we
    cannot resolve."""
    records = []
    detected = {
        "Product Name & Packing": "product_name",
        "Opeing Stock": "opening_stock",
        "Purchase Qty.": "purchase_stock",
        "Sales Qty.": "sales_qty",
        "Closing Qty": "closing_stock",
    }
    start_idx = 0
    for idx, row in enumerate(rows[:20]):
        if len(row) > 0 and "product name" in str(row[0]).lower():
            start_idx = idx + 1
            break
    for raw_row in rows[start_idx:]:
        if not any(raw_row):
            continue
        # Stop at the "NEAR EXPIRY DATAILS FOR 6 MONTHS" annex (see parse_fawin_stock).
        if cell_text(raw_row[0] if raw_row else "").strip().upper().startswith("NEAR EXPIRY"):
            break
        product = cell_text(raw_row[0] if len(raw_row) > 0 else "")
        if not _is_data_row(raw_row, product):
            continue
        record = {"product_name": product}
        if len(raw_row) > 4:
            record["opening_stock"] = to_number(raw_row[4])
        if len(raw_row) > 5:
            record["purchase_stock"] = to_number(raw_row[5])
        if len(raw_row) > 9:
            record["sales_qty"] = to_number(raw_row[9])
        if len(raw_row) > 11:
            record["closing_stock"] = to_number(raw_row[11])
        records.append(record)
    return records, detected


def parse_fawin_stock(rows):
    """Fawin "STOCK & SALES STATMENT" export.

    The header is TWO rows: a group-label band (Opeing / Purchase / Sales / L.M.S. /
    Purc. / SALES / Closing / ORDER ...) over a sub-label row (Stock / QTY. / Return /
    ... / Product Name & Packing). The columns SHIFT between vendor exports — e.g. the
    real Closing-qty sits at col 11 for most vendors but at col 10 for the ASHISH
    variant (whose col 11 is an empty ORDER column). The old parser read fixed indices
    and so mis-read closing as the empty ORDER column on that variant (closing all-zero
    -> sanity failed). We instead resolve each field from the (group, sub) header pair.
    """
    grp = sub = None
    for i, row in enumerate(rows[:8]):
        flat = " ".join(_norm(c) for c in row)
        if grp is None and "opeing" in flat and "closing" in flat:
            grp = i
        if sub is None and "productname" in flat:
            sub = i
    # Combined-header variant (MALOO): "PRODUCT NAME & PACKING" shares the group band,
    # so grp == sub. The sub-labels ("Stock"/"QTY.") live on the NEXT row. Promote sub
    # to that row so the (group, sub) resolver runs instead of the fixed-index legacy.
    if grp is not None and sub is not None and sub == grp and grp + 1 < len(rows):
        nxt = [_norm(c) for c in rows[grp + 1]]
        if "stock" in nxt and any("qty" in c for c in nxt):
            sub = grp + 1

    # Need the two distinct header rows to resolve columns; else fall back to legacy.
    if grp is None or sub is None or grp == sub:
        return _legacy_fixed_index(rows)

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
        elif g == "sales" and "qty" in s and "fr" not in s and "sales_qty" not in cmap:
            cmap["sales_qty"] = i
        # SUPRIYA MEDICAL AGENCY variant: the free-issue column is a SECOND "SALES"
        # group whose sub-label is exactly "FR." (normalises to "fr"). The freesale
        # rule below never matches it, so sales_free was silently dropped and closing
        # under-reconciled by the free qty on every discounted line (RED/AMBER x8).
        # Exact-match on s == "fr" so no other vendor's sub-label can be stolen
        # (SWASTIK's free column is group "freesale"/sub "qty" and stays on that rule).
        elif g == "sales" and s == "fr" and "sales_free" not in cmap:
            cmap["sales_free"] = i
        elif g == "freesale" and "qty" in s and "sales_free" not in cmap:
            cmap["sales_free"] = i
        elif g == "closing" and "qty" in s and "value" not in s and "closing_stock" not in cmap:
            cmap["closing_stock"] = i

    # Without a real opening+closing pair we cannot trust the resolution; use legacy.
    if "opening_stock" not in cmap or "closing_stock" not in cmap:
        return _legacy_fixed_index(rows)

    pidx = cmap.get("product_name", 0)
    start = max(grp, sub) + 1
    records = []
    for raw_row in rows[start:]:
        if not any(raw_row):
            continue
        # The export appends a "NEAR EXPIRY DATAILS FOR 6 MONTHS" annex sub-table
        # after the last division's totals. Everything past that marker is batch-level
        # expiry stock with a different column shape and must not become stock rows.
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
        "Closing Qty": "closing_stock",
    }
    return records, detected
