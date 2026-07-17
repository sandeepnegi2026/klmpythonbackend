"""Prompt ERP 'Stock Statement (Datewise)' — full-Amount KLM variants.

Report family header (top line):  Sr No. Product Name Pack OpStk Pur Sales ClStk
Numeric sub-header (2nd line) comes in TWO printed geometries under this family;
both are handled here (routed on the exact compact sub-header run — see detect.py):

  A) DOUBLE-AMOUNT  (OMKAR/COSMO Q, PATEL/KLM1):
        Qty | Qty | Qty | Amount | Qty | Amount | A3Mn | E/E | Age | Exp
     -> OpStk.Qty  Pur.Qty  Sales.Qty  Sales.AMOUNT  ClStk.Qty  ClStk.AMOUNT  (+stats)
     6 core numbers: opening / purchase / sales_qty / sales_value / closing / closing_value.

  B) FREE/INST      (SHAH MEDICINE, ALL CARE):
        Qty | Qty | Qty | Free | Inst | Qty | Amount | A3Mn | Order(s)
     -> OpStk.Qty  Pur.Qty  Sales.Qty  Sales.FREE  Sales.INST  ClStk.Qty  ClStk.AMOUNT (+stats)
     7 core numbers; sales_inst is a Prompt outward-stat we DROP; closing = ClStk.Qty,
     closing_value = Amount.  Reconcile: closing = opening + purchase - sales_qty - sales_free.

Why a dedicated layout (not base `prompt`):
  * The base `prompt` else-branch maps vals[3]->sales_free and vals[6]->sales_value,
    which for geometry A puts Sales.AMOUNT into sales_free and A3Mn into sales_value, and
    reads ClStk.AMOUNT into closing_stock (false SANITY). For geometry B it drops the
    closing VALUE (Amount) and mis-labels it sales_value.
  * The base `prompt` `ashok` branch only fires when "Amount" is GLYPH-MERGED to "mount"
    (compact 'qtymountqtyamount', SHRI ASHOK) AND there is NO Free column; these files
    print the full word 'Amount' ('qtyqtyqtyamount...'), so they miss that branch. Gating
    on the full-Amount runs keeps SHRI ASHOK (already GREEN) on its existing route.

NEVER derives qty from a value column: opening/purchase/sales_qty/closing are the printed
Qty cells; sales_value/closing_value are the printed Amount cells (kept separate).
"""
import re

from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_numbers,
    _split_product_pack,
)


def parse_prompt_datewise_amount_cols(text):
    low = text.lower().replace(" ", "")
    # Geometry B carries the Free+Inst sales columns ('qtyqtyqtyfreeinst...'); geometry A
    # is the double-Amount form. If neither sub-header run is present, fall back to the
    # double-Amount mapping (the detect gate only routes these two runs here).
    free_inst = "qtyqtyqtyfreeinstqtyamount" in low

    records = []
    for line in text.splitlines():
        s = line.strip()
        if _skip_line(s):
            continue
        # data rows start with a serial index; band/total/footer lines do not
        if not re.match(r"^\d+\s", s):
            continue
        s = re.sub(r"^\d+\s+", "", s)

        # Strip the trailing Order(s) block, e.g. "14 0 / 0 / 0 = 0" or "2 0 / 0 = 0",
        # so the trailing-number pop below stops at the real stat tail (A3Mn).
        s = re.sub(r"\s+\d+\s*/.*$", "", s)

        prod, tail, exp = _split_product_numbers(s)
        if not prod:
            continue
        vals = _nums(tail)

        name, pack = _split_product_pack(prod)

        if free_inst:
            # Op.Qty | Pur.Qty | Sales.Qty | Sales.Free | Sales.Inst | ClStk.Qty | Amount | A3Mn
            # (8 stat numbers). This vendor prints a BARE-NUMBER pack unit ("... TAB 1",
            # "... 1") that glues onto the front of the tail, so FRONT indexing would read
            # the pack count as opening_stock. The 8 stat cells always sit at the RIGHT
            # (Order(s) already stripped, A3Mn is the last number), so anchor from the end
            # and treat any leading surplus number as the pack unit.
            if len(vals) < 8:
                # short row (missing A3Mn / trailing zeros collapsed) — front map as-is
                if len(vals) < 6:
                    continue
                stat = vals
            else:
                stat = vals[-8:]
            r = {
                "product_name": name,
                "pack": pack,
                "opening_stock": stat[0],
                "purchase_stock": stat[1],
                "sales_qty": stat[2],
                "sales_free": stat[3],
                # stat[4] = Sales.Inst (Prompt outward stat) dropped
                "closing_stock": stat[5],
            }
            if len(stat) >= 7:
                r["closing_stock_value"] = stat[6]  # 'Amount' = closing stock VALUE
        else:
            # Op.Qty | Pur.Qty | Sales.Qty | Sales.Amount | ClStk.Qty | ClStk.Amount | A3Mn | ...
            if len(vals) < 5:
                continue
            r = {
                "product_name": name,
                "pack": pack,
                "opening_stock": vals[0],
                "purchase_stock": vals[1],
                "sales_qty": vals[2],
                "sales_value": vals[3],   # Sales.AMOUNT
                "closing_stock": vals[4],
            }
            if len(vals) >= 6:
                r["closing_stock_value"] = vals[5]  # ClStk.AMOUNT

        if exp:
            r["expiry"] = exp
        records.append(r)

    return records
