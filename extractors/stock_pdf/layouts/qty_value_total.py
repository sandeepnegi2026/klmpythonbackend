import re

from extractors.stock_pdf.constants import SKIP_RE, SUBTOTAL_RE
from extractors.stock_pdf.parse_common import (
    _nums,
    _split_product_numbers,
    _split_product_pack,
)


def _skip(s):
    """Local skip for this layout.

    Deliberately does NOT reuse parse_common._skip_line: that helper drops every
    line starting with "KLM " to filter the division BANDS (KLM BABY, KLM COSMO,
    ...), but this vendor also sells KLM-branded PRODUCTS (KLM KLIN FACE WASH,
    KLM C 1000, KLM FX-180 TAB, ...) whose rows would then be lost. Here the
    division bands are separated structurally instead — they carry no trailing
    numbers and fail the len(tail) == 9 gate below — so the "KLM " clause is
    intentionally omitted and the SUBTOTAL/SKIP header filters are kept.
    """
    if not s or len(s) < 5:
        return True
    if SUBTOTAL_RE.match(s) or SKIP_RE.match(s):
        return True
    if re.match(r"^[\d\s\-]+$", s):
        return True
    return False


def parse_qty_value_total(text):
    """Qty+Value pairs with a standalone Total column.

    Layout (e.g. "Sales & Stock Statement" exports, division-banded):
        PRODUCT [PACK]
        OPEN_QTY OPEN_VAL  RECEIPT_QTY RECEIPT_VAL  TOTAL_QTY
        ISSUE_QTY ISSUE_VAL  CLOSE_QTY CLOSE_VAL

    i.e. exactly 9 numbers per row, where Receipt == Purchase and Issue == Sales.
    Differs from value_pairs (4 clean qty/value pairs = 8 numbers) by the extra
    standalone TOTAL_QTY column (= opening + receipt) between receipt and issue.
    """
    # Two extended tails, each gated on a header token unique to its export so no
    # existing 8/9-number file changes:
    #   10 numbers — GEETA appends a NEAR-EXPIRY count after Closing (drop vals[9]).
    #   11/12 numbers — SIDDHI appends Dump Stock + MSR Price (drop vals[9], vals[10];
    #     a 12-tail carries a stray name digit, so take the LAST 11).
    low = text.lower()
    _c = low.replace(" ", "")
    has_near = "closingbalanear" in _c or "nearexp" in _c or "n.e.value" in _c
    has_dump_msr = "dump" in _c and "msr" in _c

    records = []
    for line in text.splitlines():
        s = line.strip()
        if _skip(s):
            continue
        prod, tail, exp = _split_product_numbers(s)
        # Structural lock: only rows carrying the movement numbers — 9 for the
        # standalone-TOTAL_QTY export, or 8 for the ZISHAN "Sales & Stock
        # Statement" sibling (4 qty/value pairs; its pair-2 value is the running
        # TOTAL value = opening_val + receipt_val, so purchase_value is not
        # emitted there). Bands/furniture carry no trailing numbers and drop out.
        if not prod or len(tail) not in (8, 9, 10, 11, 12):
            continue
        name, pack = _split_product_pack(prod)
        vals = _nums(tail)
        if len(vals) == 10 and has_near:
            # OpQ OpV RcptQ RcptV TotalQ IssQ IssV ClosQ ClosV NearExp -> map first 9.
            vals = vals[:9]
        elif len(vals) in (11, 12) and has_dump_msr:
            # ...ClosQ ClosV Dump MSR (12: stray glued name digit leads) -> LAST 11,
            # then keep the 9 movement numbers (drop Dump vals[9] and MSR vals[10]).
            vals = vals[-11:][:9]
        elif len(vals) in (10, 11, 12) and not has_near and not has_dump_msr:
            # Bare-number PACK (tablets/capsules: "ENZOTRET 10", "ONITRAZ CAP 10")
            # or a name-strength ("RESOTEN 20 10") that _split_product_numbers pulled
            # into the number tail as LEADING extra(s). GM/ML packs keep a unit letter
            # and stay in the name, so only unit-less packs leak here. The 9 movement
            # columns are always the TRAILING 9; the leading number(s) are pack/size.
            #
            # SAFETY (reconcile-gated): accept ONLY if the trailing 9 satisfy this
            # layout's own identities  Total == Opening + Receipt  AND
            # Closing == Opening + Receipt - Sales. If the extra had instead been a
            # TRAILING column (e.g. an un-flagged Age/value), the trailing-9 window is
            # shifted and these identities fail, so the row drops EXACTLY as before.
            # This branch fires only for 10/11-number rows with no near/dump header —
            # cases the parser currently drops outright — so it can only RECOVER rows
            # and can never alter one already extracted by the 8/9/near/dump paths.
            n_lead = len(vals) - 9
            cand = vals[-9:]
            lead_toks = tail[:n_lead]
            if (all("." not in t and "," not in t for t in lead_toks)   # pack/size are integers
                    and abs(cand[4] - (cand[0] + cand[2])) < 0.5        # Total == Op + Receipt
                    and abs(cand[7] - (cand[0] + cand[2] - cand[5])) < 0.5):  # Close == Op+Rec-Sale
                if not pack and lead_toks:
                    pack = lead_toks[-1]              # last leaked number is the PACK
                if n_lead > 1:                        # earlier leaked number(s) = name strength
                    name = (name + " " + " ".join(lead_toks[:-1])).strip()
                vals = cand
            # else: vals stays length 10/11 -> falls through to the else below (dropped)
        if len(vals) == 9:
            r = {
                "product_name": name,
                "pack": pack,
                "opening_stock": vals[0],
                "opening_value": vals[1],
                "purchase_stock": vals[2],
                "purchase_value": vals[3],
                "total_stock": vals[4],
                "sales_qty": vals[5],
                "sales_value": vals[6],
                "closing_stock": vals[7],
                "closing_stock_value": vals[8],
            }
        elif len(vals) == 8:
            # OP q/v | Receipt qty + TOTAL value | Issue q/v | Closing q/v.
            # Verified: Closing = OP + Receipt - Issue on every reference row
            # (EKRAN SOFT: 24+98-122=0; HISTABIL M: 10+0-0=10) and the report's
            # own TOTAL line (401+535-926=10).
            r = {
                "product_name": name,
                "pack": pack,
                "opening_stock": vals[0],
                "opening_value": vals[1],
                "purchase_stock": vals[2],
                "sales_qty": vals[4],
                "sales_value": vals[5],
                "closing_stock": vals[6],
                "closing_stock_value": vals[7],
            }
        else:
            continue
        if exp:
            r["expiry"] = exp
        records.append(r)
    return records
