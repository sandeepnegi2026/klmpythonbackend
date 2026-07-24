"""SREE SWATHI / SRIMATHA "STOCK AND SALES STATEMENT" (DOSPrinter 3.4 export).

A KLM-distributor stock-and-sales statement printed by DOSPrinter. Two vendor
skins share ONE column grid:

  * SREE SWATHI MEDICALS   -> one PDF per KLM division, single "Company Name : KLM
    <DIVISION>" header, numeric product codes (e.g. 403, 3416.), one footer block
    ("Opening Value Rs. ... Closing Value Rs. ...").
  * SRIMATHA MEDICAL HALL  -> one multi-page PDF, many divisions banded as
    "Company :KLM <DIVISION>" ... "<DIVISION> Company Total", alphanumeric codes
    (KLM080, KL0034, KLMN), a per-company footer block and a final "Grand Total :".

Column header (re-printed on every page):

    Code  Product Name  Packing  Opening  Receipts  Total  Sales  Closing  Closing
                                 Stock                            Stock    Value

True 9-column order and canonical mapping (the money column is LAST):

    Code          -> dropped (row id)
    Product Name  -> product_name
    Packing       -> pack
    Opening       -> opening_stock      (qty)
    Receipts      -> purchase_stock     (qty, inflow)
    Total         -> DERIVED (= Opening + Receipts); DROPPED
    Sales         -> sales_qty          (qty, outflow)
    Closing       -> closing_stock      (qty)  <-- the real closing stock QTY
    Closing Value -> closing_stock_value (rupees)  <-- money, NOT closing_stock

    division      -> from the "Company [Name] : KLM <DIVISION>" band header.

Why this module exists (the mis-map the audit found): generic mapped sales_qty
from the DERIVED "Total" column and closing_stock from the money "Closing Value"
column. This module maps by the real column order, so the postprocess stock
identity holds exactly:

    closing_stock == opening_stock + purchase_stock - sales_qty            (all rows)

Reconcile (verified on every file):
    sum(closing_stock_value) == printed "Closing Value Rs." footer / Grand Total,
    to the paisa; and the per-row identity above holds on every emitted row.
    e.g. CAS.PDF 22538.31, CAS2.PDF 13557.19, DERM2.PDF 24691.19 (qty sums
    Opening163/Receipts238/Sales158/Closing243), KLMP.PDF 21700.55,
    klmstat.pdf Grand Total 4,57,927.13.

POSITIONAL parse: text extraction glues the code+name+pack tokens together and a
naive "last-6-numbers" split cannot tell where the product NAME ends and the PACK
begins (names contain digits like "EKRAN 30", packs are "50 GM"/"1*10"/"10'S").
The grid is column-aligned, so we re-open with pdfplumber, cluster words by y-top,
and split each row on the PER-FILE header word x-positions:
  * code    : x0 < name_x0            (leading id token; dropped)
  * name    : name_x0 <= x0 < pack_x0
  * pack    : pack_x0 <= x0 < num_x0
  * numbers : x0 >= num_x0, bucketed to the nearest of the 6 column right-edges.
The anchors are re-derived from every page's header, so multi-page files and the
tiny per-vendor horizontal shift (SREE ~185.8 vs SRIMATHA ~188.2) are both handled.
"""
import io

import pdfplumber

# the 6 numeric column header labels, left-to-right, paired with the canonical key
# each maps to. "Total" is derived (Opening+Receipts) and dropped.
_NUM_COLS = [
    ("Opening", "opening_stock"),
    ("Receipts", "purchase_stock"),
    ("Total", "_total"),          # DERIVED = Opening + Receipts -> dropped
    ("Sales", "sales_qty"),
    ("Closing", "closing_stock"),
    ("ClosingValue", "closing_stock_value"),
]

# lower-cased line prefixes that are never product rows (headers / footers / rules)
_SKIP_PREFIXES = (
    "code product name", "product name", "stock stock value", "stock value",
    "opening value", "receipt value", "sales value", "closing value",
    "grand total", "-----", "srimatha", "sree swathi", "sree matha",
    "from :", "to :", "page :", "dosprinter", "company total",
)


def _to_f(t):
    try:
        return float(t.replace(",", "").rstrip("."))
    except ValueError:
        return 0.0


def _is_num_token(t):
    """A right-column numeric cell: optional leading '-', digits, commas, one dot."""
    s = t.replace(",", "").rstrip(".")
    if s.startswith("-"):
        s = s[1:]
    return bool(s) and any(c.isdigit() for c in s) and all(
        c.isdigit() or c == "." for c in s
    )


def _cluster_rows(page):
    """Yield rows (lists of words) clustered by y-top, each x-sorted."""
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
    return [sorted(by_top[t], key=lambda w: w["x0"]) for t in sorted(by_top)]


def _header_anchors(row):
    """If `row` is the "Code Product Name Packing Opening ... Closing" header,
    return (name_x0, pack_x0, num_x0, [(key, x1), ...]); else None."""
    toks = [w["text"] for w in row]
    if "Packing" not in toks or "Opening" not in toks or "Receipts" not in toks:
        return None
    by_text = {}
    for w in row:
        by_text.setdefault(w["text"], []).append(w)

    product = by_text.get("Product") or by_text.get("Code")
    packing = by_text["Packing"][0]
    opening = by_text["Opening"][0]

    # name starts just left of the "Product"/"Code" label; pack starts at "Packing".
    name_x0 = (product[0]["x0"] - 2.0) if product else 40.0
    pack_x0 = packing["x0"] - 1.0
    # numbers begin midway between the Packing label's right edge and Opening's
    # left edge (pack values sit under Packing; numbers are right-aligned right of it).
    num_x0 = (packing["x1"] + opening["x0"]) / 2.0

    # right-edge (x1) anchor for each of the 6 numeric columns, in header order.
    # "Closing" appears twice (Closing stock, then Closing Value); take them L->R.
    closings = sorted(by_text.get("Closing", []), key=lambda w: w["x0"])
    anchors = []
    for label, key in _NUM_COLS:
        if key == "closing_stock":
            w = closings[0] if len(closings) >= 1 else None
        elif key == "closing_stock_value":
            w = closings[1] if len(closings) >= 2 else None
        else:
            w = by_text.get(label, [None])[0]
        if w is None:
            return None
        anchors.append((key, w["x1"]))
    return name_x0, pack_x0, num_x0, anchors


def _bucket_numbers(nums, anchors):
    """Assign each numeric word to the nearest column by right-edge (x1) distance."""
    out = {}
    for w in nums:
        key = min(anchors, key=lambda kv: abs(kv[1] - w["x1"]))[0]
        out[key] = _to_f(w["text"])
    return out


def _division_from_band(line):
    """'Company :KLM COSMO (BALU)' / 'Company Name : KLM COSMO DIVISION' -> KLM ...
    Returns the division string, or None if not a company-band line."""
    low = line.lower()
    if not low.startswith("company"):
        return None
    # take text after the first ':'
    if ":" not in line:
        return None
    val = line.split(":", 1)[1].strip()
    # SRIMATHA glues "Company :KLM..." so the value already lacks a space; ok.
    return val or None


def parse_sree_swathi_stock_sales_statement(text, file_bytes=None):
    if not file_bytes:
        return []

    records = []
    anchors = None
    name_x0 = pack_x0 = num_x0 = None
    division = None

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            for row in _cluster_rows(page):
                hdr = _header_anchors(row)
                if hdr is not None:
                    name_x0, pack_x0, num_x0, anchors = hdr
                    continue
                if anchors is None:
                    continue

                line = " ".join(w["text"] for w in row).strip()
                low = line.lower()

                band = _division_from_band(line)
                if band is not None:
                    division = band
                    continue
                if not low or any(low.startswith(p) for p in _SKIP_PREFIXES):
                    continue

                nums = [w for w in row
                        if w["x0"] >= num_x0 and _is_num_token(w["text"])]
                if len(nums) < 6:
                    continue

                name_toks = [w["text"] for w in row
                             if name_x0 <= w["x0"] < pack_x0]
                pack_toks = [w["text"] for w in row
                             if pack_x0 <= w["x0"] < num_x0]
                name = " ".join(name_toks).strip()
                pack = " ".join(pack_toks).strip()
                if not name:
                    continue

                col = _bucket_numbers(nums, anchors)
                rec = {
                    "product_name": name,
                    "pack": pack,
                    "opening_stock": col.get("opening_stock", 0.0),
                    "purchase_stock": col.get("purchase_stock", 0.0),
                    "sales_qty": col.get("sales_qty", 0.0),
                    "closing_stock": col.get("closing_stock", 0.0),
                    "closing_stock_value": col.get("closing_stock_value", 0.0),
                }
                if division:
                    rec["division"] = division

                # drop fully-empty rows (every qty/value cell 0)
                if not any(rec[k] for k in (
                    "opening_stock", "purchase_stock", "sales_qty",
                    "closing_stock", "closing_stock_value",
                )):
                    continue

                records.append(rec)

    return records
