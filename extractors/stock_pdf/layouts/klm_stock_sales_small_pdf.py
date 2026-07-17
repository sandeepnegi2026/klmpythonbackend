"""KLM own-vendor "Stock sales statement Small" grid (MUDRAA PHARMA VENTURE LLP / WARAD DISTRI.).

Title:  ``Stock sales statement Small for the period <from> - <to>``
Header: Product Name | Pack | Rate | Openin(g) | Reciept | Sales | Free | SalesRt(n) | Closing

This is a WRAPPED render of an .xlsx grid (sibling of klm_stock_sales_combined_pdf).
Numbers are RIGHT-ALIGNED within their column and interior columns are frequently blank,
so a flat token-count parse cannot tell Reciept@x355 from Sales@x400 when a row omits the
zero cells (the two collapse in the extract_text stream). Product names / packs wrap across
1-3 visual lines (e.g. pack fragments '30GM' / '50GM' / '60ML' land on the following line).
We read word x-positions with pdfplumber, group wrapped lines into one product block, and
bucket every numeric token by matching its RIGHT edge (x1) to the printed header's column
right-edges.

Column map (canonical):
    Openin   -> opening_stock
    Reciept  -> purchase_stock
    Sales    -> sales_qty
    Free     -> sales_free      (OUTFLOW, per verified movement identity)
    SalesRt  -> sales_return    (ADDS back)
    Closing  -> closing_stock
    Rate     -> rate

Movement identity (holds on ~88% of rows; the residual ~12% is the vendor's own
imbalance, e.g. NIOCLEAN GEL 58+141-177-34+1 = -11 vs printed closing 51):
    Closing = Opening + Reciept - Sales - Free + SalesRt

Skipped: division band rows (``KLM - COSMO``, ``KLM - PHARMA`` ...), the two-line
value ``Total`` / ``Grand Total`` footer band (money totals whose low-order digits wrap
to a second line), and the ``Bill Nos.`` / ``Dt.`` / ``Page`` footers. Each page reprints
the vendor/title/column header; a fresh block is started per page and everything up to and
including the column header is skipped so repeated header text is never folded into a name.
"""
import io
import re

_NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*$")

# Column right-edges (header token x1), from the sampled export. Numbers are
# right-aligned so binding by right edge (x1) is robust to variable integer widths.
_ANCHORS = {
    "rate": 264.0,
    "opening_stock": 309.6,
    "purchase_stock": 355.2,
    "sales_qty": 400.8,
    "sales_free": 446.3,
    "sales_return": 491.9,
    "closing_stock": 537.5,
}
_TOL = 22.0                # x1 bucket tolerance (half a column pitch ~ 45px)

_NAME_MAX_X = 176.0        # product-name tokens live left of the Pack column
_PACK_MAX_X = 236.0        # pack tokens sit between name (176) and Rate value (~236)
_NUM_MIN_X0 = 220.0        # numeric columns begin at/after the Rate value

_SKIP_RE = re.compile(
    r"^(total|grand total|bill nos|dt\.|page\b|opening value|purchase value|"
    r"sale value|close value|value in rs)",
    re.I,
)
_BAND_RE = re.compile(r"^KLM\s*-\s*\w+", re.I)   # 'KLM - COSMO' (NOT 'KLM D3 60K CAP')
# Footer 'Bill Nos.' block wraps bill/date fragments onto continuation lines that do NOT
# start with a skip keyword (e.g. '27/0321 Dt.10-06-2026 PM/26-27/0347 ...'); a stray year
# token can bucket into a canonical column. Any line carrying a bill token / 'Dt.' is footer.
_FOOTER_RE = re.compile(r"(PM/\d|/\d\d-\d\d/|\bDt\.\d)", re.I)


def _is_num(t):
    t = t.replace(",", "")
    return bool(_NUM_RE.fullmatch(t)) and any(c.isdigit() for c in t)


def _to_f(t):
    try:
        return float(t.replace(",", ""))
    except ValueError:
        return 0.0


def _lines(words, tol=3):
    """Group words that share a visual baseline (top within tol px)."""
    by_top = {}
    for w in words:
        by_top.setdefault(round(w["top"]), []).append(w)
    lines = []
    for top in sorted(by_top):
        merged = None
        for ex_top, ex in lines:
            if abs(ex_top - top) <= tol:
                merged = ex
                break
        if merged is not None:
            merged.extend(by_top[top])
        else:
            lines.append((top, list(by_top[top])))
    return [(t, sorted(ws, key=lambda w: w["x0"])) for t, ws in lines]


def _find_anchors(lines):
    """Locate the single-line column header and return {field: right_edge_x1}."""
    for top, ws in lines:
        texts = {w["text"].lower(): w for w in ws}
        if "rate" in texts and "openin" in texts and "reciept" in texts and \
           "sales" in texts and "closing" in texts:
            def x1(key):
                return texts[key]["x1"]
            # Free / SalesRt may be absent from a header render; fall back to defaults.
            a = {
                "rate": x1("rate"),
                "opening_stock": x1("openin"),
                "purchase_stock": x1("reciept"),
                "sales_qty": x1("sales"),
                "closing_stock": x1("closing"),
            }
            if "free" in texts:
                a["sales_free"] = x1("free")
            if "salesrt" in texts:
                a["sales_return"] = x1("salesrt")
            merged = dict(_ANCHORS)
            merged.update(a)
            return merged
    return None


def _bucket(x1, anchors):
    field, dist = None, None
    for f, ax in anchors.items():
        d = abs(ax - x1)
        if dist is None or d < dist:
            field, dist = f, d
    if dist is not None and dist <= _TOL:
        return field
    return None


def _flush(block, records):
    if not block["name_lines"] and not block["frags"]:
        return
    name = " ".join(t for line in block["name_lines"] for t in line).strip()
    name = re.sub(r"\s+", " ", name)
    if not name:
        return
    low = name.lower()
    if _SKIP_RE.match(low) or _BAND_RE.match(name):
        return
    if name.replace(".", "", 1).replace(",", "").replace("-", "").isdigit():
        return

    rec = {"product_name": name, "pack": block["pack"].strip()}
    for field, frags in block["frags"].items():
        frags_sorted = sorted(frags, key=lambda f: (f[0], f[1]))
        joined = "".join(f[2] for f in frags_sorted)
        rec[field] = _to_f(joined)
    for f in ("opening_stock", "purchase_stock", "sales_qty", "sales_free",
              "sales_return", "closing_stock", "rate"):
        rec.setdefault(f, 0.0)
    # drop wholly empty product rows (no rate, no movement at all)
    if all(rec.get(f, 0.0) == 0.0 for f in
           ("rate", "opening_stock", "purchase_stock", "sales_qty",
            "sales_free", "sales_return", "closing_stock")):
        return
    records.append(rec)


def parse_klm_stock_sales_small_pdf(text, file_bytes=None):
    if not file_bytes:
        return []
    import pdfplumber

    records = []
    anchors = dict(_ANCHORS)

    def new_block():
        return {"name_lines": [], "pack": "", "frags": {}}

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            lines = _lines(page.extract_words())
            a = _find_anchors(lines)
            if a:
                anchors = a
            # Each page reprints the header; start fresh and skip through the header line.
            block = new_block()
            hdr_idx = None
            for idx, (top, ws) in enumerate(lines):
                texts = {w["text"].lower() for w in ws}
                if "rate" in texts and "openin" in texts and "reciept" in texts:
                    hdr_idx = idx
                    break
            start = 0
            if hdr_idx is not None:
                start = hdr_idx + 1
                # swallow the header continuation line ('g' / 'n' sub-tokens) if close
                if start < len(lines) and lines[start][0] - lines[hdr_idx][0] < 16:
                    start += 1
            for top, ws in lines[start:]:
                name_toks, pack_toks, num_toks = [], [], []
                for w in ws:
                    cx = w["x0"]
                    t = w["text"]
                    if _is_num(t) and cx >= _NUM_MIN_X0:
                        num_toks.append(w)
                    elif cx < _NAME_MAX_X:
                        name_toks.append(t)
                    elif cx < _PACK_MAX_X:
                        pack_toks.append(t)

                joined_name = " ".join(name_toks).strip()

                # footer / band / total lines terminate the current block and are dropped
                full_line = " ".join(w["text"] for w in ws)
                if (_SKIP_RE.match(joined_name.lower()) or _BAND_RE.match(joined_name)
                        or _FOOTER_RE.search(full_line)):
                    _flush(block, records)
                    block = new_block()
                    continue

                # A NEW product main line carries the Rate VALUE (a number whose right
                # edge sits at the Rate column ~264 and starts at x0 ~236). A wrapped
                # continuation line carries only pack fragments and/or no rate.
                rate_x = anchors.get("rate", _ANCHORS["rate"])
                has_rate = any(
                    _is_num(w["text"]) and abs(w["x1"] - rate_x) <= 6
                    and 225.0 <= w["x0"] <= 245.0
                    for w in ws
                )

                if has_rate:
                    _flush(block, records)
                    block = new_block()
                    if name_toks:
                        block["name_lines"].append(name_toks)
                    if pack_toks:
                        block["pack"] = " ".join(pack_toks)
                    for w in num_toks:
                        field = _bucket(w["x1"], anchors)
                        if field:
                            block["frags"].setdefault(field, []).append(
                                (top, w["x0"], w["text"]))
                else:
                    # continuation: wrapped name / pack unit / (rarely) wrapped digit
                    if name_toks:
                        block["name_lines"].append(name_toks)
                    if pack_toks and not block["pack"]:
                        block["pack"] = " ".join(pack_toks)
                    elif pack_toks:
                        block["pack"] = (block["pack"] + " " + " ".join(pack_toks)).strip()
                    for w in num_toks:
                        field = _bucket(w["x1"], anchors)
                        if field:
                            block["frags"].setdefault(field, []).append(
                                (top, w["x0"], w["text"]))
            _flush(block, records)
            block = new_block()

    return records
