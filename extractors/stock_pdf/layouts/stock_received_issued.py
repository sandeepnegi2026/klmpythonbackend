import io
import re

from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_numbers,
    _split_product_pack,
)


def _parse_stock_received_issued_text(text):
    """Flat-text (positional-by-order) parser.

    vals[0]=opening, vals[1]=received (purchase), vals[2]=issued (sales),
    vals[3]=closing, vals[4]=RplQty (replacement qty, ignored).
    Reconciles: closing = opening + received - issued.

    NOTE: this parser assigns the 4 movement columns purely by order and
    requires >=4 numbers per line, so it silently drops any product that
    prints a BLANK in one of the Opening/Received/Issued/Closing columns.
    The positional (x-position) parser below recovers those rows; this text
    parser is kept as a fallback for when file_bytes is unavailable.
    """
    records = []
    for line in text.splitlines():
        s = line.strip()
        if _skip_line(s):
            continue
        prod, tail, exp = _split_product_numbers(s)
        if not prod or len(tail) < 4:
            continue
        name, pack = _split_product_pack(prod)
        vals = _nums(tail)
        if len(vals) < 4:
            continue
        r = {
            "product_name": name,
            "pack": pack,
            "opening_stock": vals[0],
            "purchase_stock": vals[1],
            "sales_qty": vals[2],
            "closing_stock": vals[3],
        }
        if exp:
            r["expiry"] = exp
        records.append(r)
    return records


# ---------------------------------------------------------------------------
# Positional (pdfplumber word x-position) variant.
#
# The flat-text parser drops every product whose row prints a BLANK in one of
# the Opening/Received/Issued/Closing columns, because it assigns the surviving
# numbers positionally and then requires >=4 of them. This variant reads word
# x-positions and buckets each numeric cell into its column by RIGHT edge
# (columns are right-aligned) against the header anchors, so blank columns stay
# empty and all printed products (including single/triple-value rows) are kept.
# ---------------------------------------------------------------------------

_NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*$")
_HDR_REQUIRED = ("Opening", "Received", "Issued", "Closing")
_COLS = ["Opening", "Received", "Issued", "Closing", "RplQty"]
_FIELD = {
    "Opening": "opening_stock",
    "Received": "purchase_stock",
    "Issued": "sales_qty",
    "Closing": "closing_stock",
}


def _pos_is_num(t):
    t = t.replace(",", "")
    return bool(_NUM_RE.fullmatch(t)) and any(c.isdigit() for c in t)


def _pos_to_f(t):
    try:
        return float(t.replace(",", ""))
    except ValueError:
        return 0.0


def _pos_fmt(v):
    if v == int(v):
        return str(int(v))
    return ("%.2f" % v).rstrip("0").rstrip(".")


def _pos_header_anchors(words):
    by_text = {}
    for w in words:
        by_text.setdefault(w["text"], w)
    if not all(t in by_text for t in _HDR_REQUIRED):
        return None
    anchors = {}
    for name in _COLS:
        if name in by_text:
            anchors[name] = by_text[name]["x1"]
    # name/pack region ends where the Opening column begins; use its x0 minus pad
    name_cut = by_text["Opening"]["x0"] - 6.0
    return anchors, name_cut


def _parse_stock_received_issued_positional(file_bytes):
    import pdfplumber

    records = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            by_top = {}
            for w in words:
                by_top.setdefault(round(w["top"]), []).append(w)

            anchors = None
            name_cut = None
            order = None
            x1s = None
            cur = None  # currently-open product record being assembled

            def flush(rec):
                if not rec:
                    return
                mv = (rec.get("opening_stock"), rec.get("purchase_stock"),
                      rec.get("sales_qty"), rec.get("closing_stock"))
                if not any(v not in (None, 0.0) for v in mv):
                    return
                out = {"product_name": rec["name"]}
                if rec.get("pack"):
                    out["pack"] = rec["pack"]
                for c in ("Opening", "Received", "Issued", "Closing"):
                    out[_FIELD[c]] = (
                        _pos_fmt(rec.get(_FIELD[c], 0.0))
                        if rec.get(_FIELD[c]) is not None
                        else "0"
                    )
                records.append(out)

            for top in sorted(by_top):
                row = sorted(by_top[top], key=lambda w: w["x0"])
                found = _pos_header_anchors(row)
                if found:
                    anchors, name_cut = found
                    order = [c for c in _COLS if c in anchors]
                    x1s = [anchors[c] for c in order]
                    continue
                if not anchors:
                    continue

                joined = "".join(w["text"] for w in row)
                low_join = joined.lower()
                if joined and set(joined) <= set("-"):
                    continue

                name_words = [
                    w for w in row
                    if w["x1"] <= name_cut and not _pos_is_num(w["text"])
                ]
                name = " ".join(w["text"] for w in name_words).strip()
                nums = [
                    w for w in row
                    if _pos_is_num(w["text"]) and w["x0"] >= name_cut
                ]
                # pack candidates: tokens in name region that look like a pack
                pack = None
                alpha_name_parts = []
                for w in name_words:
                    t = w["text"]
                    if re.match(r"^\d", t) or (
                        re.search(r"\d", t) and len(t) <= 6 and w["x0"] > 140
                    ):
                        pack = t.lower()
                    else:
                        alpha_name_parts.append(t)
                name = " ".join(alpha_name_parts).strip()

                low = name.lower()
                # report summary band words
                if low in ("opening value", "purchase", "sales", "closing value"):
                    continue

                # totals band: 'GroupTotal :' line or a nameless row of huge
                # (>= 10000) values -> stop assembling (do not absorb into a
                # product). These print the report grand totals.
                if "grouptotal" in low_join:
                    break
                if not (name and any(c.isalpha() for c in name)) and \
                        any(_pos_to_f(w["text"]) >= 10000 for w in nums):
                    break

                # bucket numbers into columns by right edge
                col = {}
                for w in nums:
                    xr = w["x1"]
                    best_i, best_d = None, 14.0
                    for i, xc in enumerate(x1s):
                        d = abs(xr - xc)
                        if d < best_d:
                            best_d, best_i = d, i
                    if best_i is not None:
                        col[order[best_i]] = _pos_to_f(w["text"])

                has_name = bool(name) and any(c.isalpha() for c in name)

                if has_name:
                    # starting a new product -> flush the previous one
                    flush(cur)
                    cur = {"name": name, "pack": pack}
                    for c in ("Opening", "Received", "Issued", "Closing"):
                        if c in col:
                            cur[_FIELD[c]] = col[c]
                    if pack:
                        cur["pack"] = pack
                else:
                    # continuation line (wrapped cell): merge into current record
                    if cur is None:
                        continue
                    if pack and not cur.get("pack"):
                        cur["pack"] = pack
                    for c in ("Opening", "Received", "Issued", "Closing"):
                        if c in col and _FIELD[c] not in cur:
                            cur[_FIELD[c]] = col[c]

            flush(cur)
            cur = None

    return records


def parse_stock_received_issued(text, file_bytes=None):
    """Stock & Sales with header 'Item Name Pack Opening Received Issued Closing [RplQty]'.

    When ``file_bytes`` is available, parse by header x-position so that
    products with a BLANK movement column are not dropped (the flat-text
    parser requires >=4 numbers per line and silently discards such rows).
    The positional result is only used when it recovers at least as many
    rows as the flat-text parser, so already-passing files never regress;
    otherwise (or when file_bytes is absent) fall back to the text parser.

    vals[0]=opening, vals[1]=received (purchase), vals[2]=issued (sales),
    vals[3]=closing, vals[4]=RplQty (replacement qty, ignored).
    Reconciles: closing = opening + received - issued.
    """
    text_records = _parse_stock_received_issued_text(text)
    if file_bytes:
        try:
            pos_records = _parse_stock_received_issued_positional(file_bytes)
        except Exception:
            pos_records = []
        # Only adopt the positional result when it does not lose rows relative
        # to the flat-text parser (guards against layout mismatches).
        if len(pos_records) >= len(text_records) and pos_records:
            return pos_records
    return text_records
