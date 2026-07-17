from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_numbers,
    _split_product_pack,
)


def parse_stock_opbal_free_expiry(text):
    """KLM/SwilERP 'Sales & Stock Statement' — Op.Bal/Receipt/Total/Issue/Free/Expiry/Closing.

    Header (SHANTI MEDICOS, one section per KLM division — COSMO, PEDIA, PHARMA...):
        PRODUCT NAME  PACKING  Op.Bal.  Receipt  Total  Issue  Free Q  Expiry    Closing
                               Qty.     Qty.     Qty.   Qty.   Qty     Breakage  Balance

    Exactly SEVEN trailing qty columns per row:
        vals[0]=Op.Bal   vals[1]=Receipt   vals[2]=Total (= Op.Bal + Receipt, ignored)
        vals[3]=Issue    vals[4]=Free Q (free issued outflow)
        vals[5]=Expiry Breakage (always 0 in this export, ignored)
        vals[6]=Closing Balance

    This is the CAPITAL 'Sales & Stock Statement' (capital_stock_sale_stmt:
    Op.Bal/Receipt/Total/Issue/Closing) with two EXTRA interior columns — Free Q
    and Expiry Breakage — inserted between Issue and Closing. The base simple4 rule
    (which pops only the FIRST 4 of the 7 numbers) mis-maps Total -> sales_qty and
    Issue -> closing_stock, dropping Free/Expiry/the real Closing -> false SANITY.

    Reconcile identity: Closing = Op.Bal + Receipt - Issue - Free.  The Free Q is an
    OUTFLOW (issued-free), so it maps to sales_free; postprocess subtracts sales_free
    in expected = op + pur + pf - pr - sal - sf + sr. Expiry Breakage does not
    participate (folded nowhere; it is 0 across this export).

    Distinct from:
      * capital_stock_sale_stmt: 5 numbers/row, no Free/Expiry columns.
      * medtraders_sales_stock_statement: TWO Free-Q columns AROUND Total
        (Op.Bal|Receipt|Free|Total|Issue|Free|Closing), compact run
        'freeqtotalissuefreeqclosing'. Here the single Free Q sits AFTER Issue,
        giving compact run 'totalissuefreeqexpiryclosing'.
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
            "closing_stock": vals[6],
        }
        if exp:
            r["expiry"] = exp
        records.append(r)
    return records
