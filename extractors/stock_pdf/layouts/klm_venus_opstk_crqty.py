"""Venus "Stock and Sale Statement" (KLM division) — page-split OpStk…CrQty | ClStk…Order.

Venus prints this KLM stockist statement glyph-interleaved (item code digits woven
between the product-name letters, e.g. "XNAIO01C3L8EAN GEL" for "NIOCLEAN GEL") AND
too wide for one page, so each logical page is split across two physical pages:

    LEFT page  header: Item | Mar 26 | Apr 26 | OpStk | P.Qty | P.Val | P.Sch | S.Qty | S.Sch | S.Val | CrQty
    RIGHT page header:                                                              CrSchQty | ClStk | ClVal | Order

The product name + all movement columns are on the LEFT page; the closing stock
(ClStk) and closing value (ClVal) are on the RIGHT page, aligned to the same row top.
marg_opstk_statement descrambles the glyphs but parses each page independently, so the
right-page closing rows (which carry no product name) are dropped and every left row
ends up with closing = 0 → false SANITY_FAILED. This parser reuses the same
character-run descrambler but PAIRS left page i with right page i+1 by row top.

Mapping (right-aligned, bucketed by header right-edge):
    opening_stock = OpStk   purchase_stock = P.Qty   purchase_free = P.Sch  purchase_value = P.Val
    sales_qty     = S.Qty   sales_free     = S.Sch   sales_value   = S.Val  sales_return   = CrQty
    closing_stock = ClStk (right page)   closing_stock_value = ClVal (right page)

Reconciles: ClStk = OpStk + P.Qty + P.Sch − S.Qty − S.Sch + CrQty (verified e.g. NIOCLEAN
GEL 41 + 60 − 54 = 47 = ClStk; EPISERT 76 = 76 no-movement). Mar/Apr are previous-month
sales (left of OpStk) and are excluded. Distinct from marg_opstk_statement by the CrQty
column and the ABSENCE of a StkAd column (the detect gate keys on crqty + not stkad).
"""
import re

from extractors.stock_pdf.layouts.marg_opstk_statement import _extract_clean_words_from_pdf
from extractors.stock_pdf.parse_common import _split_product_pack

_LEFT_MAP = {
    "OPSTK": "opening_stock", "P.QTY": "purchase_stock", "P.VAL": "purchase_value",
    "P.SCH": "purchase_free", "S.QTY": "sales_qty", "S.SCH": "sales_free",
    "S.VAL": "sales_value", "CRQTY": "sales_return",
}
_RIGHT_HDR = {"CRSCHQTY", "CLSTK", "CLVAL", "ORDER"}
_NUM_RE = re.compile(r"^-?\d[\d,]*\.?\d*$")


def _is_num(t):
    t = t.replace(",", "")
    return bool(_NUM_RE.match(t)) and any(c.isdigit() for c in t)


def _to_f(t):
    try:
        return float(t.replace(",", "").rstrip("."))
    except ValueError:
        return 0.0


def _headers(words, wanted):
    """{HEADER_TOKEN: x1} for header labels present on this page."""
    return {w["text"].upper(): w["x1"] for w in words if w["text"].upper() in wanted}


def _rows_by_top(words):
    rows = {}
    for w in words:
        key = None
        for y in rows:
            if abs(y - w["top"]) < 4.0:
                key = y
                break
        rows.setdefault(key if key is not None else w["top"], []).append(w)
    return rows


def _nearest(x1, anchors):
    """Header token whose right-edge is nearest x1 (within 16pt), else None."""
    best, bd = None, 16.0
    for name, ax in anchors.items():
        d = abs(x1 - ax)
        if d < bd:
            best, bd = name, d
    return best


def _closing_for_row(rwords, rhdr):
    """Extract (ClStk, ClVal) from a right-page row, splitting a glued 'stk.val' token."""
    clstk_x = rhdr.get("CLSTK", 112.0)
    clval_x = rhdr.get("CLVAL", 154.0)
    stk = val = None
    for w in sorted(rwords, key=lambda w: w["x0"]):
        t = w["text"].replace(",", "")
        # A ClStk (int) and ClVal (decimal) printed with no gap merge into one two-dot
        # token that starts in the ClStk column and ends in the ClVal column
        # ("76.16611.32" -> 76 / 16611.32). This fails the single-dot _is_num, so handle
        # it first, gated on spanning both columns so a normal decimal is never split.
        m = re.match(r"^(\d+)\.(\d+\.\d+)$", t)
        if m and w["x0"] <= clstk_x + 4 and w["x1"] >= clval_x - 8:
            if stk is None:
                stk = float(m.group(1))
            if val is None:
                val = float(m.group(2))
            continue
        if not _is_num(t):
            continue
        tgt = _nearest(w["x1"], {"CLSTK": clstk_x, "CLVAL": clval_x})
        if tgt == "CLSTK" and stk is None:
            stk = _to_f(t)
        elif tgt == "CLVAL" and val is None:
            val = _to_f(t)
    return stk or 0.0, val or 0.0


def parse_klm_venus_opstk_crqty(text, file_bytes=None):
    if not file_bytes:
        return []
    words = _extract_clean_words_from_pdf(file_bytes)
    if not words:
        return []

    by_page = {}
    for w in words:
        by_page.setdefault(w["page"], []).append(w)
    pages = sorted(by_page)

    records = []
    division = ""
    i = 0
    while i < len(pages):
        lp = by_page[pages[i]]
        lhdr = {k: v for k, v in _headers(lp, set(_LEFT_MAP)).items()}
        if "OPSTK" not in lhdr:
            i += 1
            continue

        # pair with the next page if it carries the closing columns
        close_by_top = {}
        paired = False
        if i + 1 < len(pages):
            rp = by_page[pages[i + 1]]
            rhdr = _headers(rp, _RIGHT_HDR)
            if "CLSTK" in rhdr:
                paired = True
                for top, rws in _rows_by_top(rp).items():
                    close_by_top[round(top)] = _closing_for_row(rws, rhdr)

        min_data_x = min(lhdr.values()) - 15.0  # excludes the Mar/Apr prev-month columns
        ordered = [k for k, _ in sorted(lhdr.items(), key=lambda kv: kv[1])]
        for top, lws in sorted(_rows_by_top(lp).items()):
            lws = sorted(lws, key=lambda w: w["x0"])
            name_toks, col = [], {}
            for w in lws:
                t = w["text"].replace(",", "")
                # An adjacent qty+value pair printed with no gap merges into one two-dot
                # token ("4.4597.002" = S.Sch 4 + S.Val 4597.002). Split it: the decimal
                # part is the value column (nearest x1), the integer part its paired qty
                # column immediately to the left.
                m2 = re.match(r"^(\d+)\.(\d+\.\d+)$", t)
                if m2 and w["x1"] > min_data_x:
                    dec_tok = _nearest(w["x1"], lhdr)
                    if dec_tok:
                        if dec_tok not in col:
                            col[dec_tok] = float(m2.group(2))
                        idx = ordered.index(dec_tok)
                        if idx > 0 and ordered[idx - 1] not in col:
                            col[ordered[idx - 1]] = float(m2.group(1))
                    continue
                if _is_num(t) and w["x1"] > min_data_x:
                    tgt = _nearest(w["x1"], lhdr)
                    if tgt and tgt not in col:
                        col[tgt] = _to_f(t)
                elif not _is_num(t):
                    name_toks.append(w["text"])

            raw = " ".join(name_toks).strip()
            up = raw.upper()
            if re.match(r"^KLM\s", raw, re.I):
                division = raw
                continue
            if (not raw or up.startswith(("ITEM", "STOCK AND SALE", "VENUS", "PLOT"))
                    or "DIVISION" in up or "DIVISON" in up or not col):
                continue

            name, pack = _split_product_pack(raw)
            name = re.sub(r"^[A-Z]{1,2}\d{3,5}\s*", "", name).strip()
            if not name or len(name) < 3:
                continue

            # closing from the paired right-page row (allow +/-2px top jitter)
            stk = val = 0.0
            if paired:
                cv = close_by_top.get(round(top))
                if cv is None:
                    for dt in (1, -1, 2, -2):
                        if round(top) + dt in close_by_top:
                            cv = close_by_top[round(top) + dt]
                            break
                if cv:
                    stk, val = cv

            rec = {"product_name": name, "pack": pack, "division": division}
            for htok, field in _LEFT_MAP.items():
                if htok in col:
                    rec[field] = col[htok]
            rec["closing_stock"] = stk
            rec["closing_stock_value"] = val
            records.append(rec)

        i += 2 if paired else 1
    return records
