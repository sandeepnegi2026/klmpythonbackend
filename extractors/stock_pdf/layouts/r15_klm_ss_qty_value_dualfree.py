from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_numbers,
    _split_product_pack,
)


def parse_klm_ss_qty_value_dualfree(text):
    """KLM 'Sales & Stock Statement' — Qty+Value variant with dual Free-Q columns.

    (DUTTA MEDICOS export.) The header renders as two physical lines that collapse
    to this compact column run:

        PRODUCT NAME  PACKING
        Op.[Qty] | Opening Bal[Value]
        Receipt[Qty] | Free Q | Receipt/Pur[Value]
        Total[Qty]
        Issue[Qty] | Free Q | Issue/Sales[Value]
        Closing[Qty] | Closing Bala[Value]

    So each product row carries EXACTLY 11 trailing numbers (a Qty/Value pair per
    measure, with a standalone Total-Qty column and a dedicated Free-Q cell inside
    BOTH the Receipt and the Issue blocks):

        [0] Op.Qty          [1] Opening Value
        [2] Receipt Qty     [3] Receipt Free Q   [4] Receipt/Pur Value
        [5] Total Qty       (= Op + Receipt + Receipt-Free — printed cross-check)
        [6] Issue Qty       [7] Issue Free Q     [8] Issue/Sales Value
        [9] Closing Qty     [10] Closing Value

    Distinct from the plain ``qty_value_total`` sibling (9 numbers: no Free-Q cells)
    and from ``medtraders_sales_stock_statement`` (7 numbers: qty-only, no Value
    columns). The coarse ``qty_value_total`` gate ("opening bal"+"receipt/pur"+
    "issue/sales"+"closing bala") ALSO matches this header, but its parser only
    accepts 8/9-number tails so it emits 0 rows here and the pipeline falls back to
    a coarse popper that mis-maps the Value cells into qty/stock -> ~70% false
    SANITY_FAILED. Gated ABOVE qty_value_total on the two-Free-Q run below.

    Mapping (canonical, purchase_return = sales_return = 0):
        opening_stock       <- Op.Qty          (vals[0])
        opening_value       <- Opening Value   (vals[1])
        purchase_stock      <- Receipt Qty     (vals[2])
        purchase_free       <- Receipt Free Q  (vals[3])
        purchase_value      <- Receipt Value   (vals[4])
        total_stock         <- Total Qty       (vals[5], cross-check, informational)
        sales_qty           <- Issue Qty       (vals[6])
        sales_free          <- Issue Free Q    (vals[7])
        sales_value         <- Issue Value     (vals[8])
        closing_stock       <- Closing Qty     (vals[9])
        closing_stock_value <- Closing Value   (vals[10])

    Reconciles: closing = opening + purchase + purchase_free - sales - sales_free
    on 198/202 reference rows; the 4 exceptions carry a genuine half-strip Issue
    Free (0.50 / 2.50) that the vendor rounds off in the printed Closing (source
    rounding artifact, not a mapping error).
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
        if len(vals) < 11:
            continue
        # Take the LAST 11 numeric cells; a stray leading pack digit that survived
        # tokenization folds back into the product name.
        core = vals[-11:]
        if len(vals) > 11:
            lead = vals[:-11]
            lead_toks = [str(int(x)) if x == int(x) else str(x) for x in lead]
            prod = (prod + " " + " ".join(lead_toks)).strip()
        name, pack = _split_product_pack(prod)
        r = {
            "product_name": name,
            "pack": pack,
            "opening_stock": core[0],
            "opening_value": core[1],
            "purchase_stock": core[2],
            "purchase_free": core[3],
            "purchase_value": core[4],
            "total_stock": core[5],
            "sales_qty": core[6],
            "sales_free": core[7],
            "sales_value": core[8],
            "closing_stock": core[9],
            "closing_stock_value": core[10],
        }
        if exp:
            r["expiry"] = exp
        records.append(r)
    return records
