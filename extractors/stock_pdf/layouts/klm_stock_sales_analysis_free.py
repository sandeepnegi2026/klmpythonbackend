from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_numbers,
    _split_product_pack,
)


def parse_klm_stock_sales_analysis_free(text):
    """KLM 'STOCK & SALES ANALYSIS (KLM <DIV>)' — the per-company export with a
    "Reorder : Sale X .." option (VANDANA MEDICAL AGENCIES). IDENTICAL 14-column
    two-line header as marg_stock_analysis_full (SIDDHIVINAYAK):

        ITEM | OPENING | PURCHASE     | S/R      | REPL/OTHER | TOTAL | SALES        | SAMPLE | P/R | REPL/OTHER | CLOSING | M.EXP
               STOCK[0]  QTY[1] FREE[2] QTY[3] FREE[4] OTHER[5]  STOCK[6] QTY[7] FREE[8] [9]  T/F[10] [11]  STOCK[13]

        TOTAL(6) = OPENING(0) + every inflow(1..5)
        CLOSING(13) = TOTAL(6) - every outflow(7..12)

    UNLIKE marg_stock_analysis_full (which FOLDS free into purchase/sales because
    SIDDHIVINAYAK prints HALF-unit free goods that would not survive per-column
    integer rounding), this export prints WHOLE-unit purchase/sale free goods, so we
    keep them in their own canonical fields — purchase_free[2] and sales_free[8] —
    which the report then shows separately (the reason for this dedicated layout:
    a folded "17+3=20" purchase reads wrong to the user). The secondary movement
    columns have no canonical home, so they fold to preserve reconciliation exactly:
      - inflows S/R qty[3] + S/R free[4] + repl/other[5]  -> sales_return  (+)
      - outflows sample[9] + t/f[10] + other[11] + [12]   -> purchase_return (-)

    Reconcile (== triage sanity, qty-only body; footer prints VALUE totals only):
        closing = opening + purchase + purchase_free + sales_return
                  - sales_qty - sales_free - purchase_return
                = TOTAL - (sales_qty + sales_free + secondary outflows) = CLOSING.

    The strength that sits with the name ("HERPIVAL 1000 3'S") is stashed whole in
    _prestrip_name so enrichment matches the correct variant (Herpival-1 G, not the
    default Herpival-500) instead of the bare "HERPIVAL" stub.
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
        if len(vals) < 14:
            continue
        v = vals[-14:]  # guard against a stray leading name-number in the tail
        name, pack = _split_product_pack(prod)
        r = {
            "product_name": name,
            "pack": pack,
            "opening_stock": v[0],
            "purchase_stock": v[1],
            "purchase_free": v[2],
            # secondary inflows (S/R qty + S/R free + repl/other) add back to stock
            "sales_return": v[3] + v[4] + v[5],
            "total_stock": v[6],
            "sales_qty": v[7],
            "sales_free": v[8],
            # secondary outflows (sample + t/f + other) subtract from stock
            "purchase_return": v[9] + v[10] + v[11] + v[12],
            "closing_stock": v[13],
        }
        # NOTE: do NOT stash _prestrip_name here. When the split strands a strength in
        # the pack ("HERPIVAL 1000 3'S" -> name "HERPIVAL", pack "1000 3'S"), the core
        # enrichment's _recover_pack_strength re-matches name+pack and snaps to the
        # correct variant (Herpival-1 G). A _prestrip_name would suppress that path
        # (it is gated on no-prestrip) and the prestrip's full-name preference cannot
        # resolve the mg<->G equivalence (canonical "1 G" carries no "1000"), so the
        # row would fall back to the default sibling (Herpival-500).
        if exp:
            r["expiry"] = exp
        records.append(r)
    return records
