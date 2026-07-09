"""KLM own-vendor "Stock sales statement(Combined)" grid (VISION HEALTHCARE HOLDINGS).

Title:  ``Stock sales statement(Combined) for the period <from> - <to>``
Header: Product Name | Pack | Rate | Prev.Sale | Opening | Purchase | Total Sale |
        Sale Value | Adj. | Total Closing | Closing Value

Movement identity (verified on every sampled row):
    Total Closing = Opening + Purchase - Total Sale
``Prev.Sale`` and ``Adj.`` are informational and are DELIBERATELY not mapped to any
canonical qty field (the same defensive pattern klm_dstk_stock uses for its IN/OUT
transfer columns) so they cannot steal opening/purchase/sales/closing.

Why a positional (word x-position) parser and not the flat-text tabular fallback: this
PDF is a wrapped render of an .xlsx grid. Numbers are RIGHT-ALIGNED within their column
and long values wrap their low-order digits onto the next visual line (e.g. Rate 277.66
prints as ``277.6`` then ``6``; Sale Value 15091.44 prints as ``15091.4`` then ``4``),
while product names wrap across 2-4 lines and interior columns are frequently blank. A
flat token-count parse collapses/loses columns and mis-maps the rupee VALUE columns into
qty fields. We instead read word x-positions with pdfplumber, group the wrapped lines into
one product block, and bucket every number fragment into its column by matching its RIGHT
edge (x1) to the printed header's column right-edges, concatenating fragments per column
to reconstruct the wrapped value.

Skipped: division band rows (``KLM - C1`` / ``KLM - C2``), the ``Total Value`` /
``Total`` / ``Bill Nos.`` / ``AMP/...`` / ``Dt....`` footer block, page headers/footers,
and any row whose product cell is numeric.
"""
import io
import re

_NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*$")

# Header label -> canonical field, keyed on the RIGHT edge (x1) of the header token that
# sits at each numeric column's right margin. We DELIBERATELY do NOT include Prev.Sale or
# Adj. so those informational columns cannot steal a canonical field.
#   Rate         header 'Rate'    right edge
#   Opening      header 'Openi'   right edge
#   Purchase     header 'Purch'   right edge
#   Total Sale   header 'Total'   (1st) right edge
#   Sale Value   header 'Value'   (1st, below 'Sale') right edge
#   Total Closing header 'Total'  (2nd) right edge
#   Closing Value header 'Value'  (2nd, below 'Closing') / 'Closing' right edge
_NAME_MAX_X = 135.0        # product-name tokens live left of the Pack column
_PACK_MAX_X = 176.0        # pack tokens sit between name and Rate
_NUM_MIN_X0 = 165.0        # numeric columns begin at/after Rate

# Fallback anchors (right edges) if the header cannot be located, taken from the sampled
# export. Order matters only via the field list below.
_FALLBACK = {
    "rate": 200.0,
    "prev": 237.0,
    "opening_stock": 274.0,
    "purchase_stock": 311.0,
    "sales_qty": 353.0,
    "sales_value": 399.0,
    "adj": 436.0,
    "closing_stock": 487.0,
    "closing_stock_value": 538.0,
}


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
    """Locate the two-line column header and return {field: right_edge_x}."""
    for i, (top, ws) in enumerate(lines):
        texts = {w["text"].lower(): w for w in ws}
        if "rate" in texts and ("openi" in texts or "opening" in texts) and (
            "purch" in texts or "purchase" in texts
        ):
            # 'Total' appears twice (Total Sale, Total Closing); 'Value' twice on the
            # continuation line. Collect by scanning this header line + the next one.
            hdr = list(ws)
            if i + 1 < len(lines) and lines[i + 1][0] - top < 16:
                hdr = hdr + lines[i + 1][1]
            hdr = sorted(hdr, key=lambda w: w["x0"])
            totals = [w for w in hdr if w["text"].lower() == "total"]
            rate = texts.get("rate")
            openi = texts.get("openi") or texts.get("opening")
            purch = texts.get("purch") or texts.get("purchase")
            if not (rate and openi and purch and len(totals) >= 2):
                continue
            total_sale, total_closing = totals[0], totals[1]
            # Sale Value right edge: the 'Value' word beneath 'Sale' (left of Adj.)
            values = [w for w in hdr if w["text"].lower() == "value"]
            if len(values) < 2:
                continue
            sale_value, closing_value = values[0], values[1]
            return {
                "rate": rate["x1"],
                "opening_stock": openi["x1"],
                "purchase_stock": purch["x1"],
                "sales_qty": total_sale["x1"],
                "sales_value": sale_value["x1"],
                "closing_stock": total_closing["x1"],
                "closing_stock_value": closing_value["x1"],
            }
    return None


# Order used to resolve nearest-anchor buckets. Prev.Sale (237) and Adj. (436) are
# intentionally present ONLY as decoy buckets so numbers landing there are discarded.
def _bucket_defs(anchors):
    anchors = anchors or {}
    defs = [
        ("rate", anchors.get("rate", _FALLBACK["rate"])),
        ("_prev", _FALLBACK["prev"]),
        ("opening_stock", anchors.get("opening_stock", _FALLBACK["opening_stock"])),
        ("purchase_stock", anchors.get("purchase_stock", _FALLBACK["purchase_stock"])),
        ("sales_qty", anchors.get("sales_qty", _FALLBACK["sales_qty"])),
        ("sales_value", anchors.get("sales_value", _FALLBACK["sales_value"])),
        ("_adj", _FALLBACK["adj"]),
        ("closing_stock", anchors.get("closing_stock", _FALLBACK["closing_stock"])),
        ("closing_stock_value",
         anchors.get("closing_stock_value", _FALLBACK["closing_stock_value"])),
    ]
    return defs


def _bucket(x1, defs):
    return min(defs, key=lambda d: abs(d[1] - x1))[0]


_SKIP_RE = re.compile(
    r"^(total value|total|bill nos|amp/|dt\.|page\b|opening value|purchase value|"
    r"sale value|close value|value in rs|grand total)",
    re.I,
)
_BAND_RE = re.compile(r"^KLM\s*-\s*\w+$", re.I)


def _flush(block, defs, records):
    """Turn one accumulated product block into a record."""
    if not block["name_lines"] and not block["frags"]:
        return
    name = " ".join(t for line in block["name_lines"] for t in line).strip()
    name = re.sub(r"\s+", " ", name)
    if not name:
        return
    low = name.lower()
    if _SKIP_RE.match(low) or _BAND_RE.match(name.strip()):
        return
    # numeric-only product cell -> not a product
    if name.replace(".", "", 1).replace(",", "").replace("-", "").isdigit():
        return

    rec = {"product_name": name, "pack": block["pack"].strip()}
    for field, frags in block["frags"].items():
        if field in ("_prev", "_adj"):
            continue
        # frags is a list of (top, x0, text); concatenate in reading order to rebuild
        # a value whose low-order digits wrapped onto a later line.
        frags_sorted = sorted(frags, key=lambda f: (f[0], f[1]))
        joined = "".join(f[2] for f in frags_sorted)
        rec[field] = _to_f(joined)
    # zero-fill the movement fields so reconciliation math is well-defined
    for f in ("opening_stock", "purchase_stock", "sales_qty",
              "closing_stock", "closing_stock_value", "sales_value", "rate"):
        rec.setdefault(f, 0.0)
    # drop wholly empty rows (product with no rate and no movement at all)
    if all(rec.get(f, 0.0) == 0.0 for f in
           ("rate", "opening_stock", "purchase_stock", "sales_qty", "closing_stock")):
        return
    records.append(rec)


def parse_klm_stock_sales_combined_pdf(text, file_bytes=None):
    if not file_bytes:
        return []
    import pdfplumber

    records = []
    anchors = None
    defs = _bucket_defs(None)

    def new_block():
        return {"name_lines": [], "pack": "", "frags": {}}

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            lines = _lines(page.extract_words())
            if anchors is None:
                a = _find_anchors(lines)
                if a:
                    anchors = a
                    defs = _bucket_defs(anchors)
            # A product never wraps across a page break: every page re-prints the
            # vendor/title/column-header band. Start each page with a fresh block and
            # skip everything up to (and including) the two-line column header, so the
            # repeated header/title text can never be folded into a product name.
            block = new_block()
            hdr_idx = None
            for idx, (top, ws) in enumerate(lines):
                texts = {w["text"].lower() for w in ws}
                if "rate" in texts and ("openi" in texts or "opening" in texts) and (
                    "purch" in texts or "purchase" in texts
                ):
                    hdr_idx = idx
                    break
            start = 0
            if hdr_idx is not None:
                start = hdr_idx + 1
                # swallow the header continuation line (Sale/ng/ase/Value...) if close
                if start < len(lines) and lines[start][0] - lines[hdr_idx][0] < 16:
                    start += 1
            for top, ws in lines[start:]:
                # is this a NEW product main line? -> it carries the Rate VALUE. The real
                # Rate value starts at the left of the Rate column (x0 ~ 178) and ends at
                # its right edge (x1 ~ 200). A WRAPPED low-order rate digit on a
                # continuation line lands at the SAME right edge but starts far right
                # (x0 ~ 195, a lone char), so gating on x0 distinguishes them.
                rate_x = (anchors or _FALLBACK).get("rate", _FALLBACK["rate"])
                has_rate = any(
                    _is_num(w["text"]) and abs(w["x1"] - rate_x) <= 6
                    and 170.0 <= w["x0"] <= 186.0
                    for w in ws
                )
                # collect name / pack / number tokens for this visual line
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

                # footer / band lines terminate the current block and are dropped
                if _SKIP_RE.match(joined_name.lower()) or _BAND_RE.match(joined_name):
                    _flush(block, defs, records)
                    block = new_block()
                    continue

                if has_rate:
                    # start of a new product: flush the previous one
                    _flush(block, defs, records)
                    block = new_block()
                    if name_toks:
                        block["name_lines"].append(name_toks)
                    if pack_toks:
                        block["pack"] = " ".join(pack_toks)
                    for w in num_toks:
                        field = _bucket(w["x1"], defs)
                        block["frags"].setdefault(field, []).append(
                            (top, w["x0"], w["text"]))
                else:
                    # continuation of the current product (wrapped name / pack unit /
                    # wrapped low-order digit of a value)
                    if name_toks:
                        block["name_lines"].append(name_toks)
                    if pack_toks and not block["pack"]:
                        block["pack"] = " ".join(pack_toks)
                    elif pack_toks:
                        block["pack"] = (block["pack"] + " " + " ".join(pack_toks)).strip()
                    for w in num_toks:
                        field = _bucket(w["x1"], defs)
                        block["frags"].setdefault(field, []).append(
                            (top, w["x0"], w["text"]))
        _flush(block, defs, records)

    return records
