import re

from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_numbers,
    _split_product_pack,
)

# UNIVERSAL MEDICAL AGENCY prints the pack as a SPACE-SEPARATED token
# ('EKRAN AQUA GEL  1 * 50  295 ...') sitting between the product name and RATE.
# Because '*'/'X' is not numeric, _split_product_numbers' right-to-left tail walk
# stops at it and pulls the trailing pack digit ('50', '10', ...) into the numeric
# run, shifting every column by one (RATE read as opening-qty, opening-VALUE read
# as purchase, ...) -> 56% of rows fail stock reconciliation.
#
# Every GREEN sibling that shares this exact header instead writes the pack GLUED
# into ONE token ('1*50GR', '1X50GR', '1*10', '6*8TAB') or omits it entirely, so
# _split_product_numbers already leaves it in the product text and the columns line
# up. Collapsing ONLY the standalone spaced form '<digits> <*|X> <digits>' back into
# a single glued token reproduces the GREEN-sibling shape without touching those
# already-single-token packs: the gate ('*'/'X' with whitespace on BOTH sides)
# provably never fires on a glued pack, so rows without the spaced form are byte-
# identical to before.
_SPACED_PACK_RE = re.compile(r"(?<=\s)(\d+)\s+([*xX])\s+(\d+)(?=\s)")


def _pairs_reconcile(vals, o):
    """opening + receipt - issue == closing at alignment offset `o` (2% tol)."""
    if len(vals) < o + 7:
        return False
    return abs((vals[o] + vals[o + 2] - vals[o + 4]) - vals[o + 6]) <= max(abs(vals[o + 6]), 1.0) * 0.02


def parse_value_pairs(text):
    """Marg Qty-Value Pairs: product [RATE] OPEN_QTY OPEN_VAL RECEIPT_QTY RECEIPT_VAL ISSUE_QTY ISSUE_VAL CLOSE_QTY CLOSE_VAL [DUMP] [M.EXP]"""
    records = []
    for line in text.splitlines():
        s = line.strip()
        if _skip_line(s):
            continue
        # Gate: only rewrite when the standalone spaced pack is present; glued packs
        # and pack-less rows fall through unchanged (sub() is a no-op on them).
        s = _SPACED_PACK_RE.sub(r"\1\2\3", s)
        prod, tail, exp = _split_product_numbers(s)
        if not prod or len(tail) < 8:
            continue
        name, pack = _split_product_pack(prod)
        vals = _nums(tail)
        if len(vals) < 8:
            continue
        offset = 0
        if len(vals) >= 9 and vals[0] > 0:
            offset = 1
        # Bare-digit pack ("NEVLON AD MOST. LOTION 150 335.59 - 0.00 ...") swallowed into
        # the numeric tail fabricates a leading value read as RATE, shifting every column
        # (56% of rows fail reconciliation). Reconcile-guided repair (same idiom as
        # stock_oric_pairs): only when a leading value WAS taken as rate (offset==1), the
        # swallowed token is a bare integer, and the default alignment FAILS the identity
        # opening+receipt-issue=closing, return that token to the pack and realign. Decimal
        # rates (e.g. "335.59") never satisfy tail[0].isdigit(), so genuine rate rows are
        # untouched; a row that already reconciles at offset 1 never enters the branch.
        if (
            offset == 1
            and len(vals) >= 10
            and len(vals) == len(tail)
            and tail[0].isdigit()          # bare-INTEGER pack candidate
            and "." in tail[1]             # the REAL rate (a decimal) sits right after it;
                                           # a genuine integer rate (MELBOOST "10") is followed
                                           # by an integer qty, so this rejects it
            and not _pairs_reconcile(vals, offset)
        ):
            cand = _nums(tail[1:])
            cand_off = 1 if (len(cand) >= 9 and cand[0] > 0) else 0
            # Only accept the repair when returning the bare token to the pack makes the row
            # actually reconcile — otherwise leave the baseline alignment untouched.
            if len(cand) >= 8 and _pairs_reconcile(cand, cand_off):
                name, pack = _split_product_pack(prod + " " + tail[0])
                vals = cand
                offset = cand_off
        r = {
            "product_name": name,
            "pack": pack,
            "rate": vals[0] if offset else 0.0,
            "opening_stock": vals[offset],
            "opening_value": vals[offset + 1],
            "purchase_stock": vals[offset + 2],
            "purchase_value": vals[offset + 3],
            "sales_qty": vals[offset + 4],
            "sales_value": vals[offset + 5],
            "closing_stock": vals[offset + 6],
            "closing_stock_value": vals[offset + 7]
            if offset + 7 < len(vals)
            else 0.0,
        }
        if exp:
            r["expiry"] = exp
        records.append(r)
    return records
