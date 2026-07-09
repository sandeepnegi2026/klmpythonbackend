from extractors.stock_pdf.parse_common import (
    _clean_number_token,
    _is_num,
    _skip_line,
    _split_product_pack,
    _to_number,
)

# Columns after Packing: O.Stk  Purc  Tot  Sale  Qoh  Value  Age  (Tot & Age ignored).
_MAX_COLS = 7


def _split_qoh_line(s):
    """Split one raw statement line into (product+pack text, [column floats]).

    Walk tokens from the RIGHT, cleaning each per-token watermark glyph and
    dropping lone watermark letters (e.g. '... 0 0 F 0.00 393'), collecting up to
    ``_MAX_COLS`` numeric columns. Everything left of the run — product words plus
    the pack, including a bare-number pack like '10' — is returned RAW so the pack
    is never mangled. Returns (None, []) when the line is not a data row (too few
    numeric columns, e.g. the header or a division band).
    """
    toks = s.split()
    if len(toks) < 3:
        return None, []
    vals = []
    i = len(toks) - 1
    while i >= 0 and len(vals) < _MAX_COLS:
        t = toks[i]
        c = _clean_number_token(t)
        if _is_num(c):
            vals.insert(0, _to_number(c) or 0.0)
            i -= 1
            continue
        # a lone single watermark letter inside/at the tail of the number run
        # (e.g. '... 2776.23 I 19', or a trailing '... 36 R') -> drop it. Gated on
        # a numeric LEFT neighbour so a genuine name/pack token is never eaten.
        if (
            len(t) == 1
            and t.isalpha()
            and i > 0
            and _is_num(_clean_number_token(toks[i - 1]))
        ):
            i -= 1
            continue
        break
    if len(vals) < 5:
        return None, []
    return " ".join(toks[: i + 1]), vals


def parse_stock_qoh(text):
    """KLM 'Stock & Sales Statement' (Qoh = Quantity-on-hand).

    Columns: NAME PACK  O.Stk  Purc  Tot  Sale  Qoh  Value  Age
    (Tot = O.Stk + Purc; Qoh = Tot - Sale). closing = Qoh; Value is the rupee
    closing-stock value; Tot and Age are ignored.

    PROFITMAKER/DAXINSOFT exports (VISHAL/HIMALAYA/GMR/SANGLI/LAXMI/…) print a
    diagonal watermark whose single letters bleed into the text layer. We strip
    those glyphs PER-TOKEN inside the numeric column run only (see
    ``_split_qoh_line``), so legit digit+letter pack/strength suffixes to the left
    survive intact. The former whole-line clean turned 'HERPIVAL-1G 3S' into
    'HERPIVAL-1 3' AND dropped rows whose Value glyph (e.g. '1039T.50') broke the
    numeric tail — both corrected here.
    """
    records = []
    for line in text.splitlines():
        s = line.strip()
        if _skip_line(s):
            continue
        prod, vals = _split_qoh_line(s)
        if not prod:
            continue
        name, pack = _split_product_pack(prod)
        n = len(vals)
        records.append({
            "product_name": name,
            "pack": pack,
            "opening_stock": vals[0],
            "purchase_stock": vals[1],
            # vals[2] = Tot (O.Stk + Purc), ignored
            "sales_qty": vals[3] if n > 3 else 0.0,
            "closing_stock": vals[4] if n > 4 else vals[-1],
            "closing_stock_value": vals[5] if n > 5 else 0.0,
            # vals[6] = Age (days), ignored
        })
    return records
