from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_numbers,
    _split_product_pack,
)


def parse_stock_opbal_issue_expiry_near(text):
    """KLM 'Sales & Stock Statement' — Op.Bal/Receipt/Total/Issue/Expiry/Closing/Near.

    Header (AGARWAL PHARMA, one section per KLM division — COSMO Q, etc.):
        PRODUCT NAME  PACKING  Op.Bal.  Receipt  Total  Issue  Expiry     Closing  Near
                               Qty.     Qty.     Qty.   Qty.   Breakage   Balance  Expiry

    Exactly SEVEN trailing qty columns per row:
        vals[0]=Op.Bal            vals[1]=Receipt   vals[2]=Total (= Op.Bal + Receipt, ignored)
        vals[3]=Issue             vals[4]=Expiry Breakage (outflow: goods removed for expiry/breakage)
        vals[5]=Closing Balance   vals[6]=Near Expiry (near-to-expire stock, informational, ignored)

    Reconcile identity:  Closing = Op.Bal + Receipt - Issue - Expiry/Breakage.
    The Expiry Breakage cell is a genuine OUTFLOW here (e.g. EKRAN AQUA GEL:
    29 + 90 - 56 - 1 = 62), so it maps to sales_free — postprocess subtracts
    sales_free in expected = op + pur + pf - pr - sal - sf + sr. The trailing
    Near-Expiry cell is a snapshot count, not a movement, so it is dropped.

    Distinct from:
      * capital_stock_sale_stmt: 5 numbers/row, no Expiry/Near columns
        (Op.Bal/Receipt/Total/Issue/Closing) — compact run
        'op.bal.receipttotalissueclosing'.
      * stock_opbal_free_expiry (SHANTI MEDICOS): 7 numbers/row too, but the
        outflow column is a Free Q that sits BEFORE the (always-0) Expiry
        Breakage and there is NO Near column — compact run
        'totalissuefreeqexpiryclosing'. Here the Expiry Breakage sits directly
        after Issue and a Near column trails Closing — compact run
        'totalissueexpiryclosingnear' — which appears in no other stock layout.
    """
    records = []
    for line in text.splitlines():
        s = line.strip()
        if _skip_line(s):
            continue
        prod, tail, exp = _split_product_numbers(s)
        if not prod or len(tail) < 7:
            continue
        name, pack = _split_product_pack(prod)
        vals = _nums(tail)
        if len(vals) < 7:
            continue
        r = {
            "product_name": name,
            "pack": pack,
            "opening_stock": vals[0],
            "purchase_stock": vals[1],
            "sales_qty": vals[3],
            "sales_free": vals[4],
            "closing_stock": vals[5],
        }
        if exp:
            r["expiry"] = exp
        records.append(r)
    return records
