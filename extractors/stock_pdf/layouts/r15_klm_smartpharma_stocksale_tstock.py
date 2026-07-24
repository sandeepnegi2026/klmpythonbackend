import re

from extractors.stock_pdf.parse_common import _skip_line, _split_product_pack

# ---------------------------------------------------------------------------
# KLM / SmartPharma360 "Stock and Sale Report For Reps" — the 15-column
# per-division export (PRUDHVI PHARMACEUTICALS, "klm stock and sales statement
# all divisions.pdf"). Header (one physical line):
#
#   Products Pack O.stk T.Stock Purc Purc.Ret Replace. S.Qty S.Free
#            S.Value S.Ret Qty S.Ret Fre Qoh Value Age
#
# Gate token (spaces stripped, lowercased): "o.stkt.stockpurcpurc.retreplace."
#
# The coarse `"qoh" in low` rule in detect.py sends this to the generic
# `stock_qoh` layout, which knows nothing about the extra T.Stock (= opening +
# purchase, a running total, NOT a flow) or the Replace. column, so it mis-maps
# every numeric cell (it drops opening into 0 and mistakes the S.Value amount
# for purchase_stock). This dedicated parser reads all 13 numeric columns by
# their exact positions and reconciles on 100% of rows.
#
# Column meaning / canonical mapping:
#   O.stk      -> opening_stock
#   T.Stock    -> total_stock          (= O.stk + Purc; running total, informational)
#   Purc       -> purchase_stock
#   Purc.Ret   -> purchase_return
#   Replace.   -> sales_return  (a "+" inflow that adds back to stock)
#   S.Qty      -> sales_qty
#   S.Free     -> sales_free
#   S.Value    -> sales_value
#   S.Ret Qty  -> sales_return  (folded together with Replace.; both are "+")
#   S.Ret Fre  -> (free return qty; folded into sales_return "+")
#   Qoh        -> closing_stock
#   Value      -> closing_stock_value
#   Age        -> OPTIONAL trailing integer (days); ignored (no canonical home)
#
# Reconcile (== triage sanity):
#   closing = opening + purchase - purchase_return
#             + Replace. + S.Ret Qty + S.Ret Fre        (all "+" -> sales_return)
#             - sales_qty - sales_free
# Verified: KOJITIN 5 + 30 - 0 + 0 - 21 - 0 = 14 = Qoh; all 100 rows hold.
#
# Because Purc.Ret / S.Free / S.Ret* are almost always 0 here, the report is
# effectively opening + purchase - sales = closing, but every column is mapped
# to its own canonical slot (never derive a quantity from an amount column).
#
# PACK: usually a text token glued to the name ("15gm", "60ml", "1*3"); but for
# bare-dosage packs ("10", "20", "4") the pack is a pure integer that lands in
# the trailing numeric run. We right-anchor on the LAST decimal token (Value)
# to isolate the fixed 12-column data block, and any leftover leading numeric
# token(s) are the numeric pack.
# ---------------------------------------------------------------------------

_NUMTOK = re.compile(r"^-?\d+(?:\.\d+)?$")
_DEC = re.compile(r"^-?\d+\.\d+$")
_COMPANY = re.compile(r"company\s*name\s*:\s*(?:klm\s*-\s*)?(.+)$", re.I)


def _fnum(t):
    try:
        return float(t)
    except (TypeError, ValueError):
        return 0.0


def parse_klm_smartpharma_stocksale_tstock(text):
    records = []
    division = ""
    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            continue
        m = _COMPANY.search(s)
        if m:
            division = m.group(1).strip()
            continue
        # header / footer / page furniture
        low = s.lower()
        if (
            low.startswith(("products ", "page:", "stock and sale", "stock sale report"))
            or low.startswith(("powered by", "total op", "sale val", "taken by"))
            or "total closing stk" in low
            or "total replacement value" in low
        ):
            continue
        if _skip_line(s):
            continue

        toks = s.split()
        # trailing numeric run
        nums = []
        j = len(toks) - 1
        while j >= 0 and _NUMTOK.match(toks[j]):
            nums.insert(0, toks[j])
            j -= 1
        if len(nums) < 12:
            continue
        name_tokens = toks[: j + 1]
        if not name_tokens:
            continue

        # right-anchor: Value is the LAST decimal token; the 12 fixed data
        # columns end there (O.stk .. Value). Anything before is numeric pack;
        # anything after is the optional Age integer.
        dec_pos = [k for k, t in enumerate(nums) if _DEC.match(t)]
        if not dec_pos:
            continue
        vpos = dec_pos[-1]
        if vpos - 11 < 0:
            continue
        cols = nums[vpos - 11 : vpos + 1]
        pack_leftover = nums[: vpos - 11]  # numeric pack token(s), if any

        (
            ostk,
            tstock,
            purc,
            purcret,
            repl,
            sqty,
            sfree,
            sval,
            sretq,
            sretf,
            qoh,
            val,
        ) = cols

        name = " ".join(name_tokens)
        pname, pack = _split_product_pack(name)
        if pack_leftover and not pack:
            # bare-dosage numeric pack ("10", "4") absorbed into the number run
            pack = pack_leftover[-1]
        if not re.search(r"[A-Za-z]{3}", pname):
            continue

        sales_return = _fnum(repl) + _fnum(sretq) + _fnum(sretf)
        rec = {
            "product_name": pname,
            "pack": pack,
            "division": division,
            "opening_stock": _fnum(ostk),
            "total_stock": _fnum(tstock),
            "purchase_stock": _fnum(purc),
            "purchase_return": _fnum(purcret),
            "sales_qty": _fnum(sqty),
            "sales_free": _fnum(sfree),
            "sales_value": _fnum(sval),
            "sales_return": sales_return,
            "closing_stock": _fnum(qoh),
            "closing_stock_value": _fnum(val),
        }
        records.append(rec)
    return records
