from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_numbers,
    _split_product_pack,
)


def _pair_ints(main, free):
    """Integerize a (column, FREE-column) pair without losing their printed sum.

    enforce_schema int-rounds every qty field PER ROW (INT_FIELDS), so half-unit
    strips like SALE 13.50 / FREE 0.50 would round independently (13.50->14,
    0.50->0) and break the per-row closing equation by 1. The pre-split code
    folded the pair first (14.0) and only then rounded, which is why it always
    reconciled. Reproduce that: round the pair SUM, give the main column its own
    rounding, and let the FREE column absorb the remainder. Called only when a
    fractional value is present; integral pairs never reach this helper.
    """
    total = int(round(main + free))
    m = int(round(main))
    f = total - m
    if f < 0:  # free went negative after rounding (defensive; free >= 0 in data)
        m, f = total, 0
    return float(m), float(f)


def parse_marg_open_pur_free_sale(text):
    """Marg 'STOCK & SALES ANALYSIS' free-goods layout (SAUMYA PHARMACEUTICALS style).

    Header:  ITEM NAME | OPENING | PURCHASE | FREE | SALE | FREE | CLOSING | VALUE
    Sub-row:              -          -PUR RET  +REPL   -SR    +REPL

    7 numeric columns, fixed across the whole family:
        vals[0] OPENING        -> opening_stock
        vals[1] PURCHASE       (already net of purchase-return)
        vals[2] FREE (+REPL)   purchase free goods -> physically ADD to stock
        vals[3] SALE           (already net of sales-return)
        vals[4] FREE (+REPL)   sale free goods    -> physically SUBTRACT from stock
        vals[5] CLOSING        -> closing_stock
        vals[6] VALUE          -> closing_stock_value

    Both FREE columns enter the physical stock equation (verified: folding them in
    yields 100% reconciliation vs 74% when ignored). The canonical schema carries
    dedicated purchase_free / sales_free fields (reconcile: closing = opening +
    purchase_stock + purchase_free - purchase_return + sales_return - sales_qty -
    sales_free), so each FREE column is emitted on its own field instead of being
    folded into its left neighbour; purchase_return / sales_return are 0 because the
    ERP has already netted real returns into the PURCHASE / SALE columns.
    """
    records = []
    for line in text.splitlines():
        s = line.strip()
        if _skip_line(s):
            continue
        prod, tail, exp = _split_product_numbers(s)
        if not prod:
            continue
        vals = _nums(tail)
        if len(vals) < 7:
            continue
        name, pack = _split_product_pack(prod)
        if pack:
            # The shared pipeline re-runs extract_pack_from_product on product_name,
            # and PACK_RE also matches BARE form words (LOTION/CREAM/TAB/...), so a
            # residual name like "EKRAN LOTION" (pack already peeled to 50GM) would
            # lose its last word there. When the residual name still ends in such a
            # digit-less pseudo-pack token, keep the pack attached to the name: the
            # pipeline's single strip then removes the pack and the word survives.
            # All other rows are byte-identical.
            _res, _stripped = _split_product_pack(name)
            if _stripped and not any(ch.isdigit() for ch in _stripped):
                name = prod
        opening = vals[0]
        purchase = vals[1]
        purchase_free = vals[2]
        sale = vals[3]
        sale_free = vals[4]
        if purchase % 1 or purchase_free % 1:
            purchase, purchase_free = _pair_ints(purchase, purchase_free)
        if sale % 1 or sale_free % 1:
            sale, sale_free = _pair_ints(sale, sale_free)
        closing = vals[5]
        value = vals[6]
        r = {
            "product_name": name,
            "pack": pack,
        }
        if pack and pack.split()[0].isalpha() and prod != name:
            # _split_product_pack peeled a leading dosage-form word (TAB/CAP/...)
            # into the pack, leaving a bare stub ("NIOFINE TAB 1*7" -> name
            # "NIOFINE", pack "TAB 1*7"). The bare stub fuzzy-snaps to the WRONG
            # sibling SKU (NIOFINE -> "Niofine Dusting Powder"). Stash the full
            # pre-strip string so enrich_rows_with_master runs its O(1) exact
            # lookup on "NIOFINE TAB 1*7" first; on a miss it falls through to
            # today's bare-name path unchanged.
            r["_prestrip_name"] = prod
        r.update({
            "opening_stock": opening,
            "purchase_stock": purchase,
            "purchase_free": purchase_free,
            "purchase_return": 0.0,
            "sales_qty": sale,
            "sales_free": sale_free,
            "sales_return": 0.0,
            "closing_stock": closing,
            "closing_stock_value": value,
        })
        if exp:
            r["expiry"] = exp
        records.append(r)
    return records
