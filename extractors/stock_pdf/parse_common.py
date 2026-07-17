import re

import pandas as pd

from extractors.stock_pdf.constants import EXP_RE, NUM_RE, PACK_RE, SKIP_RE, SUBTOTAL_RE


def _clean(v):
    return "" if v is None else str(v).replace("\n", " ").strip()


def _to_number(v):
    t = _clean(v).replace(",", "")
    if t in ("", "-", "-----", "-----"):
        return 0.0
    t = t.rstrip(".")
    p = pd.to_numeric(pd.Series([t]), errors="coerce").iloc[0]
    return float(p) if pd.notna(p) else None


def _is_num(v):
    return _to_number(v) is not None


def _clean_number_token(t):
    """Return ``t`` as a clean numeric string when it is a number wearing a SINGLE
    diagonal-watermark letter (PROFITMAKER / DAXINSOFT / Medica-Ultimate exports
    bleed the vendor-name glyphs into the text layer); otherwise return it
    unchanged. Covers embedded ('1039T.50'->'1039.50', '0a0'->'00', '2776.2I3'->
    '2776.23'), leading ('e0'->'0', 'O51'->'51', 'F1582.90'->'1582.90') and
    trailing ('13A'->'13', '20l'->'20').

    MUST only be applied to tokens in the numeric column run — a legit digit+letter
    pack/strength ('3S','1G','10S') or a name token ('D3') would also collapse to a
    number, so callers walk the tail and stop at the first genuine non-number.
    """
    if _is_num(t):
        return t
    for pat in (
        r"(?<=[\d.])[A-Za-z](?=[\d.])",   # embedded (either side of the decimal point)
        r"^[A-Za-z](?=\d)",               # leading
        r"(?<=\d)[A-Za-z]$",              # trailing
    ):
        c = re.sub(pat, "", t, count=1)
        if c != t and _is_num(c):
            return c
    return t


def _split_product_numbers(line):
    """Universal: split a line into (product_text, [number_tokens], expiry_str)"""
    tokens = line.strip().split()
    if len(tokens) < 3:
        return None, [], ""
    tail = []
    expiry = ""
    while tokens and (NUM_RE.match(tokens[-1]) or EXP_RE.match(tokens[-1])):
        t = tokens.pop()
        if EXP_RE.match(t) and not expiry:
            expiry = t
        else:
            tail.insert(0, t)
    if not tail or not tokens:
        return None, [], ""
    return " ".join(tokens), tail, expiry


from core.pack_match import extract_pack_from_product as _split_product_pack


def _nums(tail):
    """Convert tail tokens to floats, treating '-' and '-----' as 0."""
    return [_to_number(t) or 0.0 for t in tail if _to_number(t) is not None]


def _parse_page_range(page_range, total):
    if not page_range:
        return list(range(total))
    pages = set()
    for part in str(page_range).split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            s, e = part.split("-", 1)
            pages.update(
                range(max(1, int(s or 1)), min(total, int(e or total)) + 1)
            )
        else:
            pages.add(int(part))
    return [p - 1 for p in sorted(pages) if 1 <= p <= total]


def _skip_line(s):
    if not s or len(s) < 5:
        return True
    # A bare "KLM <DIVISION>" band header (no digits) is section noise and stays skipped;
    # but "KLM"-BRANDED product rows (KLM C-1000, KLM FX 120, KLM KLIN FACE WASH …) always
    # carry a trailing numeric stat tail, so keep them — the unconditional startswith("KLM ")
    # guard silently dropped every KLM-brand SKU across all stock_pdf layouts.
    if SUBTOTAL_RE.match(s) or SKIP_RE.match(s) or (s.startswith("KLM ") and not re.search(r"\d", s)):
        return True
    if re.search(r"non moving|last \d+ months", s, re.I):
        return True
    if re.match(r"^[\d\s\-]+$", s):
        return True
    return False


def _zero_row_is_product(name) -> bool:
    """Whether an all-zero (no-movement) row is a real catalog SKU worth keeping.

    Several stock layouts list products the distributor stocks that simply had no
    movement in the period (all qty columns 0, often only a rate printed) — those
    are real rows and should be kept for completeness. A positional parser can,
    however, mis-capture a header/footer ADDRESS or contact block as a zero row.
    Real product names carry no comma and no shop/plot/property/phone token, so
    keep a named row unless it looks like such an address fragment.
    """
    name = str(name or "").strip()
    if sum(c.isalpha() for c in name) < 3:
        return False
    if "," in name:
        return False
    return not re.search(r"\b(shop|plot|property|phone)\b", name, re.I)
