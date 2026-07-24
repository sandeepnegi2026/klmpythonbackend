import re

from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_numbers,
    _split_product_pack,
)


def parse_prompt(text):
    """Prompt ERP Stock Statement text layout"""
    # SHRI ASHOK datewise variant has NO Free column: the 7-number core is
    # Op.Qty / Pur.Qty / Sales.Qty / Sales.Amount / ClStk.Qty / ClStk.Amount / A3Mn
    # (sub-header '... Qty mount Qty Amount A3Mn'). The base mapping below reads
    # Sales.Amount as sales_free and ClStk.Amount as closing qty, so gate this variant on
    # 'a3mn' + the 'qty mount qty amount' run WITHOUT a Free column.
    _low = text.lower()
    ashok = (
        "a3mn" in _low
        and "free" not in _low
        and "qtymountqtyamount" in _low.replace(" ", "")
    )
    # The 8-numeric-column datewise geometry is identified by the sub-header run
    # 'Qty Qty Qty Free Inst Qty Amount A3Mn' (OpStk Pur Sales.Qty Sales.Free Sales.Inst
    # ClStk.Qty ClStk.Amount A3Mn). ONLY on this geometry does a 9th leading numeric token
    # mean a bare-number pack size (e.g. 'TAB 10') leaked left of the OpStk column. The
    # OTHER prompt geometry ('Qty Qty Qty Amount Qty Amount A3Mn E/E Age Exp' — OMKAR,
    # ANJALI, COSMO) legitimately carries 9 numeric values with no leaked pack, so the
    # shift MUST be gated to the Free+Inst sub-header only.
    _flat = _low.replace(" ", "")
    free_inst_geom = "qtyqtyqtyfreeinstqtyamount" in _flat
    records = []
    for line in text.splitlines():
        s = line.strip()
        if _skip_line(s):
            continue

        # Lines start with an index number
        if not re.match(r"^\d+\s", s):
            continue

        # Strip index
        s = re.sub(r"^\d+\s+", "", s)

        # Strip trailing order format: "A3Mn Order(s): 3 0 / 0 / 0 = 0"
        s = re.sub(r"\s+\d+\s*/.*$", "", s)

        prod, tail, exp = _split_product_numbers(s)
        if not prod or len(tail) < 6:
            continue

        name, pack = _split_product_pack(prod)
        vals = _nums(tail)

        # vals: OpStk(0), Pur(1), Sales(2), Free(3), Inst(4), ClStk(5), Amount(6)
        if len(vals) < 6:
            continue

        if ashok:
            # Op.Qty / Pur.Qty / Sales.Qty / Sales.Amount / ClStk.Qty / ClStk.Amount / A3Mn
            r = {
                "product_name": name,
                "pack": pack,
                "opening_stock": vals[0],
                "purchase_stock": vals[1],
                "sales_qty": vals[2],
                "sales_value": vals[3],
                "closing_stock": vals[4],
                "closing_stock_value": vals[5],
                # vals[6] = A3Mn (3-month avg) dropped
            }
        else:
            # Base datewise geometry has EXACTLY 8 numeric columns after the pack:
            #   OpStk.Qty Pur.Qty Sales.Qty Sales.Free Sales.Inst ClStk.Qty ClStk.Amount A3Mn
            # A pack whose size is a BARE trailing number (e.g. "TAB 10" -> the '10' is a
            # separate right-aligned token that _split_product_pack leaves behind) leaks that
            # number into the numeric tail as a 9th leading value, shifting every column left
            # by one (OpStk<-pack, Pur<-OpStk, ...). Those rows print closing that no longer
            # reconciles (sales holds the negative purchase-return, closing collapses to a
            # later 0). When there are 9 numeric tokens, the FIRST is the leaked pack size:
            # move it into pack and read the 8-column window from vals[1:] (offset by one).
            off = 1 if (free_inst_geom and len(vals) >= 9) else 0
            if off:
                leaked = str(tail[0]).strip()
                pack = (pack + " " + leaked).strip() if pack else leaked
            r = {
                "product_name": name,
                "pack": pack,
                "opening_stock": vals[off + 0],
                "purchase_stock": vals[off + 1],
                "sales_qty": vals[off + 2],
                "sales_free": vals[off + 3],
                "closing_stock": vals[off + 5],
            }
            if len(vals) >= off + 7:
                r["sales_value"] = vals[off + 6]

        if exp:
            r["expiry"] = exp

        records.append(r)

    return records
