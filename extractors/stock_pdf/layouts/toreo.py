import re

from extractors.stock_pdf.parse_common import _clean_number_token, _is_num, _to_number

# <digits> <one letter> <digits>, no dot anywhere -> two glyph-glued integer columns
# (e.g. the always-'0' IN/OT glued to the closing STOCK: '0a6' -> '0','6').
_GLUED_INTCOL_RE = re.compile(r"^(\d+)[A-Za-z](\d+)$")

# A glued pack-unit token that carries no space before its unit letters, e.g.
# '10G' '50G' '30GM' '20GM' '150ML' '100MG'. _clean_number_token would strip the
# trailing unit and mis-read it as a data column ('10G'->'10'), shifting the whole
# numeric tail left. These belong to the PACK, not the numeric run, so the tail
# walk must STOP here. Anchored to real pharma pack units so a plain digit column
# ('10','50') is never caught.
_PACK_UNIT_TOKEN_RE = re.compile(r"^\d+(?:GM|ML|MG|KG|GML|MLL|LTR|G|L)$", re.I)


def _num(v):
    return _to_number(_clean_number_token(v)) or 0.0


def _unglue_intcols(tokens):
    """Split any <int><letter><int> token (glyph-glued adjacent integer columns)
    into its two halves. Leaves every other token untouched."""
    out = []
    for t in tokens:
        m = _GLUED_INTCOL_RE.match(t)
        # Only split when the token is NOT already a plain number — i.e. it
        # genuinely carries a stray letter between two integer groups.
        if m and not _is_num(t):
            out.append(m.group(1))
            out.append(m.group(2))
        else:
            out.append(t)
    return out


def parse_toreo_stock(text):
    """
    Toreo LTD / Sangli Medical ERP Stock Statement (Medica Ultimate).
    Headers: PRODUCT DESCRIPTION PACKING OPSTK PURCH SALE SALE VAL IN/OTSTOCK STK VAL FEB JAN...
    Columns:  0 OPSTK  1 PURCH  2 SALE  3 SALE VAL  4 IN/OT  5 STOCK(closing)  6 STK VAL  (FEB/JAN ignored)

    Medica Ultimate prints a diagonal watermark whose single letters bleed into the
    number columns ('0a0'->'00', 'e0'->'0'); left unhandled they read as alpha tokens
    and truncate the numeric tail, dropping the row. We walk the tail from the RIGHT,
    cleaning each glyph-number, and stop at the first genuine non-number (the pack
    unit / product word), so a name digit like 'D3' in 'KLM D3 60K' is never eaten.
    """
    records = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        low = line.lower()
        if "description" in low and "packing" in low and "opstk" in low:
            continue
        if "stockstatement" in low or "sangli medical" in low or "chintamani" in low:
            continue
        if "gstin" in low or "email" in low or "from date" in low:
            continue

        tokens = _unglue_intcols(line.split())
        if len(tokens) < 7:
            continue

        # collect the trailing numeric run (glyph-tolerant), stopping at the pack unit
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
            continue

        prod_pack = " ".join(tokens[: i + 1])
        records.append({
            "product_name": prod_pack,
            "opening_stock": vals[0],
            "purchase_stock": vals[1],
            "sales_qty": vals[2],
            "closing_stock": vals[5],
            "closing_stock_value": vals[6],
        })

    return records
