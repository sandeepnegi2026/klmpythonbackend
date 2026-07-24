"""J.K.MEDICO PRIVATE LIMITED (THE SAURASHTRA MEDICAL AGENCY) "Stock sales statement".

A KLM-family (RAJKOT) "Product wise sale list" exported as xlsx->pdf. It IS a real
editable %PDF-1.4 (NOT scanned) and extracts cleanly; the earlier "low-fidelity
xlsx" flag was a false alarm. The header reads:

    Product Name  Pack  Rate  Opening  Purchase  Sales  SValue  Closing  Cl.Value

9 fixed, RIGHT-aligned columns. Because the source is an xlsx re-flow, long values
overflow their cell and WRAP the trailing digit(s) / fraction onto the next physical
line, and long product names wrap onto one or more continuation lines. A flat text
extract therefore interleaves broken numbers and name fragments (e.g. Cl.Value
"10549.9" on the main line + "4" on the line below -> 10549.94). So this is parsed
POSITIONALLY: every numeric word is bucketed to its column by matching its right
edge (x1) to that column's header-label right edge, and fragments that land in the
same column within one product group are glued in top order to rebuild the number.

Column -> canonical mapping (by MEANING, per the verified audit; the generic parser
had done a 1-col LEFT shift that broke the per-row stock identity):
    Product Name -> product_name        (main line + name-only continuation lines)
    Pack         -> pack                 (x-band between name and Rate)
    Rate         -> rate                 (per-unit price; informational)
    Opening      -> opening_stock        (qty)
    Purchase     -> purchase_stock       (qty, inflow)
    Sales        -> sales_qty            (qty, outflow)
    SValue       -> sales_value          (rupees; the MONEY column mid-grid)
    Closing      -> closing_stock        (qty)
    Cl.Value     -> closing_stock_value  (rupees)

There is NO explicit purchase_free / sales_return / adjustment column, so those emit
as 0. The band lines "KLM COSMO", "KLM COSMO Q", "KLM COSMOCOR", "KLM DERMA", ...
are DIVISION headers (they start with "KLM"); every other text-only line inside the
grid is a wrapped product-NAME continuation and is appended to the current product's
name (NOT treated as a band).

Reconcile identity (verified on every moving row, e.g.
    EKRAN 30 SILICON  43 + 30 - 35 = 38 (closing),
    HISTABIL 10TAB   142 + 150 - 129 = 163,
    STUDART SOFTGEL  180 + 340 - 327 = 193):
    closing_stock == opening_stock + purchase_stock - sales_qty
which is exactly the postprocess sanity identity (purchase_free/sales_free/returns
are 0 here), so it PASSES for every printed moving row. The footer "Total" /
"Grand Total" rows carry rupee value sub-totals (paisa fractions, wrapped) under the
qty anchors and are SKIPPED as data rows; they are not per-column qty totals.
"""
import io

import pdfplumber

# Column key, in header order, paired with a FALLBACK right-edge x1 (RAJKOT geometry).
# Real anchors are derived per page from the header row; these are used only if a
# page's header could not be read.
_COLUMNS = [
    ("rate", 264.0),
    ("opening_stock", 309.6),
    ("purchase_stock", 355.2),
    ("sales_qty", 400.8),
    ("sales_value", 446.3),
    ("closing_stock", 491.9),
    ("closing_stock_value", 537.5),
]
_FALLBACK_ANCHORS = dict(_COLUMNS)

# Header-label token (left, unwrapped stem) -> canonical column key. "Openin"/"Purchas"/
# "Cl.Valu" are the wrapped stems pdfplumber emits (final letter drops to next line).
_HEADER_LABEL_KEY = {
    "rate": "rate",
    "openin": "opening_stock",
    "opening": "opening_stock",
    "purchas": "purchase_stock",
    "purchase": "purchase_stock",
    "sales": "sales_qty",
    "svalue": "sales_value",
    "closing": "closing_stock",
    "cl.valu": "closing_stock_value",
    "cl.value": "closing_stock_value",
}

# x0 below which a token is product-name (Pack column starts ~182.8).
_NAME_X1 = 175.0
# x0 band for the Pack column (between name and the Rate number column ~236).
_PACK_X0 = 175.0
_PACK_X1 = 230.0

_SKIP_STARTS = (
    "product name", "j.k.medico", "rajkot", "stock sales statement",
    "page ", "bill nos", "grand total",
)


def _is_num_frag(t):
    """A numeric fragment: digits with optional comma/dot (may be a wrapped tail)."""
    s = t.replace(",", "")
    return bool(s) and any(c.isdigit() for c in s) and all(
        c.isdigit() or c == "." for c in s
    )


def _to_f(s):
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return 0.0


def _cluster_lines(page):
    """Cluster a page's words into physical lines (by top), each x-sorted."""
    words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
    by_top = {}
    for w in words:
        key = round(w["top"])
        matched = None
        for k in by_top:
            if abs(k - key) <= 2:
                matched = k
                break
        by_top.setdefault(matched if matched is not None else key, []).append(w)
    return [(top, sorted(by_top[top], key=lambda w: w["x0"]))
            for top in sorted(by_top)]


def _header_anchors(line):
    """If `line` is the column header, return {col_key: x1}, else None."""
    got = {}
    for w in line:
        key = _HEADER_LABEL_KEY.get(w["text"].strip().lower())
        if key:
            got[key] = w["x1"]
    # need at least the money columns + opening to trust it as the header
    if "opening_stock" in got and "sales_value" in got and "closing_stock_value" in got:
        merged = dict(_FALLBACK_ANCHORS)
        merged.update(got)
        return merged
    return None


def _bucket(w, anchors):
    """Nearest column key to a numeric word by right-edge distance (<=14pt)."""
    best, bd = None, 1e9
    for key, x1 in anchors.items():
        d = abs(x1 - w["x1"])
        if d < bd:
            best, bd = key, d
    return best if bd <= 14.0 else None


def parse_jkmedico_stock_sales_statement(text, file_bytes=None):
    if not file_bytes:
        return []

    records = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        # `division` carries across page breaks: a division spans several pages but its
        # "KLM ..." band header is printed only once (on the page where it starts).
        division = None
        for page in pdf.pages:
            anchors = dict(_FALLBACK_ANCHORS)
            cur = None          # pending product record being assembled

            def flush():
                nonlocal cur
                if cur is None:
                    return
                # glue wrapped numeric fragments per column (top order preserved)
                rec = {"product_name": " ".join(cur["name"]).strip(),
                       "pack": " ".join(cur["pack"]).strip()}
                if division:
                    rec["division"] = division
                has_val = False
                for key, _ in _COLUMNS:
                    frags = cur["cols"].get(key)
                    if not frags:
                        continue
                    val = _to_f("".join(frags))
                    if key == "rate":
                        rec["rate"] = val
                    else:
                        rec[key] = val
                        if val:
                            has_val = True
                if rec["product_name"] and has_val:
                    records.append(rec)
                cur = None

            for _top, line in _cluster_lines(page):
                low = " ".join(w["text"] for w in line).strip().lower()
                if not low:
                    continue

                hdr = _header_anchors(line)
                if hdr is not None:
                    flush()
                    anchors = hdr
                    continue

                if any(low.startswith(p) for p in _SKIP_STARTS):
                    flush()
                    continue

                # bare "Total ..." footer (rupee sub-totals under qty anchors) -> skip
                if low.startswith("total"):
                    flush()
                    continue

                # division band: text-only line that starts with KLM
                nums = [w for w in line if _is_num_frag(w["text"])]
                if not nums and line and line[0]["text"].strip().upper().startswith("KLM"):
                    flush()
                    division = " ".join(w["text"] for w in line).strip()
                    continue

                name_toks = [w["text"] for w in line if w["x1"] <= _NAME_X1]
                # Pack column sits in the x-band between the name and the Rate number
                # column; it can contain digits ("50 GM", "1X10", "10CAP", "30GM"), so
                # numeric tokens are kept here as long as they fall left of the Rate col.
                pack_toks = [w["text"] for w in line
                             if _PACK_X0 < w["x0"] < _PACK_X1]
                col_nums = [w for w in nums if w["x0"] >= _PACK_X1]

                # Does this line START a new product? It does when it carries the Rate
                # or Opening column (the leftmost value columns of a main data row).
                buckets = {}
                for w in col_nums:
                    key = _bucket(w, anchors)
                    if key:
                        buckets.setdefault(key, []).append(w["text"])
                starts_product = ("rate" in buckets or "opening_stock" in buckets
                                  or "purchase_stock" in buckets or "sales_qty" in buckets)

                if starts_product:
                    flush()
                    cur = {"name": [], "pack": [], "cols": {}}

                if cur is None:
                    # stray fragment before any product on the page (rare) -> ignore
                    continue

                cur["name"].extend(name_toks)
                cur["pack"].extend(pack_toks)
                for w in col_nums:
                    key = _bucket(w, anchors)
                    if key:
                        cur["cols"].setdefault(key, []).append(w["text"])

            flush()

    return records
