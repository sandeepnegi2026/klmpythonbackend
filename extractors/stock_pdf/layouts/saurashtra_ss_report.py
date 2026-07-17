import re

from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_numbers,
    _split_product_pack,
)


def parse_saurashtra_ss_report(text):
    """Logic ERP Monthly SS Report: ItemCode ItemName Pack PRate PTR Opening PurQty ... Closing ClosingAmt.

    This format differs from saurashtra_monthly:
    - No SrNo column — lines start with item code (e.g. A02348, PROD8836)
    - No Opening Value column
    - Product names sometimes span two lines (name on line N, data on line N+1)
    - Item codes are prepended to product names and must be stripped

    Column layout (18 values per data line):
    0=PRate 1=PTR 2=Opening 3=PurQty 4=PurFQty 5=PurVal
    6=PurRetRQty 7=PurRetFQty 8=RplQty 9=SaleQty 10=SaleFQty 11=SaleVal
    12=SaleRetQty 13=SaleRetFQty 14=OtherQty
    15=Closing 16=ClosingAmt(PTR) 17=ClosingAmt(PurRate)
    """
    records = []
    lines = text.splitlines()
    pending_name = None  # Multi-line product name from previous line

    for i, line in enumerate(lines):
        s = line.strip()
        if _skip_line(s):
            pending_name = None
            continue

        # Skip header/metadata lines
        s_up = s.upper()
        header_keywords = [
            " PVT ", " LTD", "AGENCIES", "AGENCY", "MEDICOSE", "MEDICOS", "DISTRIBUTOR", "DISTRIBUTER", 
            "ENTERPRISE", "FSSAI", "GSTIN", "CONTACT", "EMAIL", "PAGE ", "STATEMENT", "COMPANY :", 
            "VENDOR :", "DIVISION NAME", "YEAR :", "MONTHLY", "MANUFACTURER", "PACK PUR", "ITEM CODE",
            "SIZE RATE", "TOTAL COUNT", "DIVISION NAME"
        ]
        if any(k in s_up for k in header_keywords):
            pending_name = None
            continue

        # Check for item code prefix pattern: A02348, PROD8836, B00708, M02949, C01920
        item_code_match = re.match(r"^([A-Z]\d{4,5}|PROD\d{3,5})\s*(.*)", s, re.I)

        if not item_code_match:
            # Line without item code — could be continuation of product name
            # e.g. "MELBOOST NXT" or "TABLETS" or "5GM"
            # Treat as pending_name if it's mostly text (not a pack-only line like "5GM")
            prod_test, tail_test, _ = _split_product_numbers(s)
            if prod_test and len(tail_test) < 4:
                # Has some text + few numbers — likely product name continuation
                pending_name = s
            elif not prod_test and len(s) >= 3 and len(s) < 50:
                # Purely text line (e.g. "MELBOOST NXT", "AMOCLAFIX 625 TABLET")
                pending_name = s
            continue

        item_code = item_code_match.group(1)
        rest = item_code_match.group(2).strip()

        if not rest:
            # Item code only line (rare) — skip
            continue

        prod, tail, _ = _split_product_numbers(rest)
        if not prod or len(tail) < 4:
            # Not enough numeric data — might be item code + partial name
            if prod:
                pending_name = prod
            continue

        vals = _nums(tail)
        if len(vals) < 10:
            continue

        name, pack = _split_product_pack(prod)

        # Strip any remaining item code prefix from name
        name = re.sub(r"^[A-Z]\d{4,5}\s*", "", name).strip()
        name = re.sub(r"^PROD\d{3,5}\s*", "", name, flags=re.I).strip()

        # If we had a pending multi-line name, prepend it
        if pending_name and name:
            name = pending_name + " " + name
        elif pending_name and not name:
            name = pending_name

        pending_name = None

        if not name or len(name) < 2:
            continue

        # Column layout (18 values):
        # 0=PRate 1=PTR 2=Opening 3=PurQty 4=PurFQty 5=PurVal
        # 6=PurRetRQty 7=PurRetFQty 8=RplQty 9=SaleQty 10=SaleFQty 11=SaleVal
        # 12=SaleRetQty 13=SaleRetFQty 14=OtherQty
        # 15=Closing 16=ClosingAmt(PTR) 17=ClosingAmt(PurRate)
        n = len(vals)
        r = {
            "product_name": name,
            "pack": pack,
            "rate": vals[0],
            "opening_stock": vals[2] if n > 2 else 0.0,
            "purchase_stock": vals[3] if n > 3 else 0.0,
            "purchase_free": vals[4] if n > 4 else 0.0,
            "purchase_value": vals[5] if n > 5 else 0.0,
            "purchase_return": vals[6] if n > 6 else 0.0,
            "sales_qty": vals[9] if n > 9 else 0.0,
            "sales_free": vals[10] if n > 10 else 0.0,
            "sales_value": vals[11] if n > 11 else 0.0,
            "sales_return": vals[12] if n > 12 else 0.0,
            "closing_stock": vals[-3] if n > 5 else vals[-1],
            "closing_stock_value": vals[-2] if n > 5 else 0.0,
        }
        records.append(r)

    return records
