import re

from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_numbers,
    _split_product_pack,
)


def parse_saurashtra_monthly(text):
    """Logic ERP Monthly Sales & Stock: SrNo ItemName PackSize PRate PTR Opening OpeningValue PurQty ... Closing ClosingAmt StockAmt

    Two dialects share the "Monthly Sales And Stock" gate. VASAVI ends every row in the
    3-tail [Closing Qty, Closing Amt(PTR), Stock Amt(Pur.Rate)] and prints Pack-Size as its
    own numeric column. WESTERN HEALTHCARE appends a trailing "Rpl. Qty" column (4-tail) AND
    prints the pack inline in the item name ("EKRAN LOTION 50GM"), so the numeric tail carries
    no leading pack. Left unhandled, the shared back-anchored mapping shifts a column (closing
    value read as closing qty) and the >=20 pop eats WESTERN's Rate. Normalise WESTERN back to
    the VASAVI shape: (1) drop the trailing Rpl column when the header carries it, (2) only pop
    a leading numeric pack when one wasn't already peeled into an alnum `pack`. Both guards are
    inert for VASAVI (no "rpl. qty" header; its pack column is always numeric -> pack == "").
    """
    records = []
    _low = text.lower()
    has_rpl = "rpl. qty" in _low or "rpl.qty" in _low
    for line in text.splitlines():
        s = line.strip()
        if _skip_line(s):
            continue
        m = re.match(r"^(\d{1,3})\s+(.+)", s)
        if not m:
            s_up = s.upper()
            # Global rule to skip ERP headers (Vendor names, addresses, pagination, etc.)
            header_keywords = [
                " PVT ", " LTD", "AGENCIES", "AGENCY", "MEDICOSE", "MEDICOS", "DISTRIBUTOR", "DISTRIBUTER", 
                "ENTERPRISE", "FSSAI", "GSTIN", "CONTACT", "EMAIL", "PAGE ", "STATEMENT", "COMPANY :", 
                "VENDOR :", "DIVISION NAME"
            ]
            if any(k in s_up for k in header_keywords):
                continue
            
            # Check for pure text line (product name continuation)
            prod_test, tail_test, _ = _split_product_numbers(s)
            if not tail_test and len(s) >= 3 and len(s) < 50:
                if records:
                    records[-1]["product_name"] += " " + s
            continue
            
        rest = m.group(2)
        prod, tail, _ = _split_product_numbers(rest)
        if not prod or len(tail) < 10:
            continue
            
        name, pack = _split_product_pack(prod)
        vals = _nums(tail)
        if len(vals) < 10:
            continue

        # WESTERN dialect: strip the trailing Rpl.Qty so the row matches VASAVI's 3-tail.
        if has_rpl and vals:
            vals = vals[:-1]

        # A leading numeric Pack-Size column is present only when the pack wasn't already
        # peeled into an alnum `pack` (WESTERN's "50GM" is inline -> its first number is Rate).
        if len(vals) >= 20 and not pack:
            numeric_pack = vals.pop(0)
            pack = str(int(numeric_pack)) if numeric_pack.is_integer() else str(numeric_pack)
            
        if len(vals) >= 19:
            r = {
                "product_name": name,
                "pack": pack,
                "rate": vals[-19],
                "opening_stock": vals[-17],
                "opening_value": vals[-16],
                "purchase_stock": vals[-15],
                "purchase_free": vals[-14],
                "purchase_value": vals[-13],
                "purchase_return": vals[-12],
                "sales_qty": vals[-10],
                "sales_free": vals[-9],
                "sales_value": vals[-8],
                "sales_return": vals[-7],
                # "Other" is Logic-ERP's signed book-vs-physical stock adjustment
                # (header col "Other Qty", index -4): + adds to closing, - removes.
                # Map to canonical `shortage` (added with its own sign in the reconcile
                # identity). Absent/zero on files without the column, so this is purely
                # additive and cannot change a currently-reconciling row's closing.
                "shortage": vals[-4],
                "closing_stock": vals[-3],
                "closing_stock_value": vals[-2],
            }
        else:
            r = {
                "product_name": name,
                "pack": pack,
                "rate": vals[0],
                "opening_stock": vals[2] if len(vals) > 2 else 0.0,
                "opening_value": vals[3] if len(vals) > 3 else 0.0,
                "purchase_stock": vals[4] if len(vals) > 4 else 0.0,
                "purchase_free": vals[5] if len(vals) > 5 else 0.0,
                "purchase_value": vals[6] if len(vals) > 6 else 0.0,
                "purchase_return": vals[7] if len(vals) > 7 else 0.0,
                "sales_qty": vals[9] if len(vals) > 9 else vals[-4],
                "sales_free": vals[10] if len(vals) > 10 else 0.0,
                "sales_value": vals[11] if len(vals) > 11 else 0.0,
                "sales_return": vals[12] if len(vals) > 12 else 0.0,
                "closing_stock": vals[-3] if len(vals) > 5 else vals[-1],
                "closing_stock_value": vals[-2] if len(vals) > 5 else 0.0,
            }
        records.append(r)
    return records
