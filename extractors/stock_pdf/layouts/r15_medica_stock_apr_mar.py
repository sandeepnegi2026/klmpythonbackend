import re

from extractors.stock_pdf.parse_common import _clean_number_token, _is_num, _to_number

# Medica Ultimate "STOCK STATEMENT" (RAHUL DISTRIBUTORS -> KLM LABORATORIES).
# Header run (spaces stripped, lowercased) that gates this format:
#   "...in/otstockstkvalaprmar..."  (the trailing APR / MAR / EXP monthly columns
#   are what distinguish it from the toreo_stock variant, whose tail is FEB JAN).
#
# Printed column order after PRODUCT DESCRIPTION:
#   [PACKING] OPSTK PURCH SALE SALE-VAL IN/OT STOCK STK-VAL [APR] [MAR] [EXP]
# where:
#   - PACKING is a bare integer ONLY for pack-less products (tablets/caps: "10",
#     "15", "20"); for creams/lotions the pack unit ("15GM", "150ML") glues into
#     the product text and there is NO leading numeric PACKING token.
#   - APR / MAR / EXP are trailing monthly-sale integers that VARY in count (0..3).
# Because both the leading PACKING and the trailing month columns are optional, a
# left- or right-anchored fixed slice mis-reads columns (that is exactly why the
# coarse toreo_stock gate mis-maps this file). Instead we isolate the stable
# 7-wide data block  [OPSTK PURCH SALE SALE-VAL IN/OT STOCK STK-VAL]  by sliding a
# window and picking the offset where the stock identity holds:
#     OPSTK + PURCH + IN/OT - SALE == STOCK(closing)
# IN/OT is a signed in/out adjustment (can be negative); it maps to +sales_return.
#
# Medica Ultimate prints a diagonal watermark whose single glyphs bleed into the
# number run ('0a13'->'0','13'; '4e0'->'40'); we un-glue those before slicing.

_GLUED_INTCOL_RE = re.compile(r"^(\d+)[A-Za-z](\d+)$")
_PACK_UNIT_TOKEN_RE = re.compile(r"^\d+(?:GM|ML|MG|KG|GML|MLL|LTR|G|L)$", re.I)

_SKIP_SUBSTR = (
    "stockstatement",
    "s t o c k",
    "description",
    "laboratories pvt",
    "distributors pvt",
    "gstin",
    "email",
    "web site",
    "from date",
    "dlno",
    "fssai",
    "cin no",
    "mobile",
    "industrial estate",
    "cross road",
    "division total",
    "end of report",
    "this pdf report",
    "page no",
)


_E_WATERMARK_RE = re.compile(r"^(\d+)[eE](\d+)$")

# Pack-unit token with a watermark 'e' bled between the unit and the FIRST data
# column, e.g. 'KLM D3 NANO SHOTS 5MLe40 ...' where '5ML' is the pack and '40' is
# OPSTK. Unlike _E_WATERMARK_RE (pure <digit>e<digit>), this token carries a real
# pack-unit suffix, so it needs splitting into ['5ML','40'] BEFORE the number run.
_PACK_E_DATA_RE = re.compile(
    r"^(\d+(?:GM|ML|MG|KG|GML|MLL|LTR|G|L))[eE](\d+)$", re.I
)


def _num(v):
    # '4e0' is a single value 40 with an 'e' bled *inside* it by the diagonal
    # watermark; pandas would read it as scientific notation (4.0), so join the
    # digits back into one integer before the generic numeric parse.
    m = _E_WATERMARK_RE.match(v)
    if m:
        v = m.group(1) + m.group(2)
    return _to_number(_clean_number_token(v)) or 0.0


def _unglue(tokens, merge_glued=False):
    """Split genuinely-glued adjacent integer columns ('0a13' -> '0','13').

    Only splits when the token is NOT already a plain number, i.e. it carries a
    real stray letter between two integer groups (the always-zero IN/OT glued onto
    the closing STOCK). A <digit>e<digit> token like '4e0' is left intact so that
    _clean_number_token can recover it as the SINGLE value '40' (the watermark bled
    an 'e' *inside* one number); pandas would misread '4e0' as scientific notation,
    which _clean_number_token corrects.

    A '<int>letter<int>' token is AMBIGUOUS: it can be two glued columns ('0a13' ->
    '0','13') OR a single value wearing a mid-number watermark letter ('5a834' ->
    '5834' -- pdfminer >=20251230 keeps the giant diagonal glyph fused into the
    SALE-VAL cell as one wide token). ``merge_glued=True`` keeps such a token whole
    so _clean_number_token collapses it to the single true value; the caller tries
    the split reading FIRST and only falls back to merged when the stock identity
    fails to reconcile, so genuinely-glued '0a13' columns are unaffected.
    """
    out = []
    for t in tokens:
        pe = _PACK_E_DATA_RE.match(t)
        if pe:
            # '5MLe40' -> '5ML' (pack unit, stops the number run) + '40' (OPSTK)
            out.append(pe.group(1))
            out.append(pe.group(2))
            continue
        m = _GLUED_INTCOL_RE.match(t)
        if m and not _is_num(t) and not merge_glued:
            out.append(m.group(1))
            out.append(m.group(2))
        else:
            out.append(t)
    return out


def _tokens_to_row(tokens):
    """(prod, vals) from an un-glued token list, or None if it can't be a data row.

    Collects the trailing numeric run (glyph-tolerant), stopping at the first
    genuine non-number / pack-unit token so a product word is never eaten.
    """
    if len(tokens) < 8:
        return None
    i = len(tokens) - 1
    vals = []
    while (
        i >= 0
        and _is_num(_clean_number_token(tokens[i]))
        and not _PACK_UNIT_TOKEN_RE.match(tokens[i])
    ):
        vals.insert(0, _num(tokens[i]))
        i -= 1
    if i < 0 or len(vals) < 7:
        return None
    prod = " ".join(tokens[: i + 1]).strip()
    if not prod or not any(c.isalpha() for c in prod):
        return None
    return prod, vals


def _reconciled_window(vals):
    """Leftmost 7-wide window satisfying OPSTK+PURCH+IN/OT-SALE == STOCK, else None."""
    for off in range(0, len(vals) - 7 + 1):
        ops, pur, sale, saleval, inot, stk, stkval = vals[off : off + 7]
        if ops + pur + inot - sale == stk:
            return vals[off : off + 7]
    return None


def parse_medica_stock_apr_mar(text):
    records = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        low = line.lower()
        if any(s in low for s in _SKIP_SUBSTR):
            continue

        raw = line.split()
        # A '<int>letter<int>' cell is ambiguous (two glued columns vs one
        # watermark-fused value). Read it BOTH ways and accept the first whose
        # 7-wide window satisfies the stock identity: split first (preserves the
        # genuine '0a13' IN/OT-glued-onto-STOCK case), then merged (recovers a
        # single-value cell like '5a834'->'5834' that pdfminer >=20251230 keeps
        # fused). Only rows where the split reading fails to reconcile change.
        prod = chosen = None
        for merge_glued in (False, True):
            r = _tokens_to_row(_unglue(raw, merge_glued=merge_glued))
            if r is None:
                continue
            win = _reconciled_window(r[1])
            if win is not None:
                prod, chosen = r[0], win
                break
        if chosen is None:
            # Neither reading reconciles (a genuinely OCR-mangled cell): fall back
            # to the split reading's first 7 columns after an optional single
            # leading PACKING token -- unchanged from the original behaviour.
            r = _tokens_to_row(_unglue(raw))
            if r is None:
                continue
            prod, vals = r
            off = 1 if len(vals) >= 8 else 0
            chosen = vals[off : off + 7]

        ops, pur, sale, saleval, inot, stk, stkval = chosen
        rec = {
            "product_name": prod,
            "opening_stock": ops,
            "purchase_stock": pur,
            "sales_qty": sale,
            "sales_value": saleval,
            "closing_stock": stk,
            "closing_stock_value": stkval,
        }
        # Signed in/out adjustment -> the +sales_return slot in the identity.
        if inot > 0:
            rec["sales_return"] = inot
        elif inot < 0:
            rec["sales_qty"] = sale - inot  # subtracting a negative adds outflow
        records.append(rec)

    return records
