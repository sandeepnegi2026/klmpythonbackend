"""ASHA AGENCIES (Bilaspur, CG) "Stock n Sales Status" report (Data Spec s/w).

Emailed PDF export. Title line prints twice (mail header + report banner):

    Stock n Sales Status - '01-May-2026' to '31-May-2026' Only Active

The stock table has a two-line grouped header (only reprinted on the FIRST data
page; later pages continue the same grid without re-printing it):

    Item Name  Opg Qty  Inw Qty  Out Qty  Clg Qty      Days Last Sale
                                                       on 30/06/26

Rows are grouped under per-division band headers ("KLM COSMO COR DIV",
"KLM COSMO DIV", ...); each group ends with a printed money-VALUE total line:

    Values: KLM COSMO COR DIV  16,472  88,645  69,521  21,176

The per-division legend (last page) confirms the meaning of the columns:
    "Opg Qty and Clg Qty at Last Purchase Rate
     Inw Qty and Out Qty at Actual Value"
so the four "Values:" numbers are the money values of the four quantity columns,
NOT quantities. They are used only as the reconcile oracle and are not emitted.

WHY POSITIONAL (not a flat text split): every zero cell prints a single '-', and
the trailing "Days Last Sale on 30/06/26" column is populated on only a handful of
rows. A flat token split therefore mis-aligns columns, and a "last-numeric-is-
closing" heuristic (what the generic parser did) leaks the Days value into closing
on the ~6 rows that carry it (e.g. IMXIA -10% LOTION prints "... 5  68" where 5 is
Clg qty and 68 is Days-since-last-sale). The four quantity columns are LEFT-aligned
to rock-stable x0 anchors, so each number is bucketed into its column by matching
its left edge (x0) to the nearest anchor, and the Days column (x0 >= ~415) is
dropped outright.

Column x0 anchors (verified stable across all data pages of the sample; a clean
5-cluster histogram at 259 / 300 / 343 / 387 / 428):

    Opg Qty  x0 ~= 259  -> opening_stock      (Last Purchase Rate valued)
    Inw Qty  x0 ~= 300  -> purchase_stock     (inflow)
    Out Qty  x0 ~= 343  -> sales_qty          (outflow)
    Clg Qty  x0 ~= 387  -> closing_stock      (the TRUE closing qty)
    Days     x0 ~= 428  -> DROPPED (days-since-last-sale, not a stock field)

Reconcile identity (postprocess.sanity_warnings) holds per row:
    closing_stock == opening_stock + purchase_stock - sales_qty
(no free / return / adjustment columns exist in this report, so those fields are
left 0 and the identity collapses to Clg = Opg + Inw - Out). Verified on 129/131
data rows; the ~2 residual rows are source anomalies (a closing printed with no
opening, and one text-extraction glue handled below), matching the audited
"123/129 identity holds" oracle. The Clg-qty column sums to ~1068, and each of the
7 per-division "Values:" money totals is printed for cross-check.

Text-glue recovery: on the "SOFIDEW BABY MOI.CREAM 100GM, 100 ML1" row the
opening-qty digit fuses onto the pack unit as a single word "ML1" whose right edge
lands inside the Opg column. Any word that starts in the name/pack area but whose
right edge crosses into the Opg band and ends in a digit run has that trailing
digit run split off as opening_stock (and stripped from the pack text).
"""
import io
import re

import pdfplumber

# Fixed left-edge (x0) anchors for the four quantity columns. Anchors are refined
# per-file from the numeric-word x0 histogram (see _derive_anchors) but default to
# the sample geometry so a page whose bands could not be measured still parses.
_DEFAULT_ANCHORS = {
    "opening_stock": 259.0,   # Opg Qty
    "purchase_stock": 300.0,  # Inw Qty
    "sales_qty": 343.0,       # Out Qty
    "closing_stock": 387.0,   # Clg Qty
}
# Numbers whose left edge is at/after this x drop into the "Days Last Sale" column.
_DAYS_X0_MIN = 415.0
# Data band starts here (names/packs sit left of this; the Opg column is the first
# thing right of it).
_DATA_X0_MIN = 250.0
# Half-width tolerance for assigning a number to an anchor (bands are ~40pt apart).
_ANCHOR_TOL = 18.0

_NUM_RE = re.compile(r"^\d[\d,]*(?:\.\d+)?$")
_GLUE_TAIL_RE = re.compile(r"^(?P<head>.*?[A-Za-z].*?)(?P<digits>\d+)$")


def _is_num(t):
    return bool(_NUM_RE.match(t))


def _to_f(t):
    try:
        return float(t.replace(",", ""))
    except ValueError:
        return 0.0


def _cluster_rows(page):
    """Cluster a page's words into visual rows by y-top (dot-matrix baselines wobble)."""
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


def _derive_anchors(pages_rows):
    """Refine the four column anchors from the numeric-word x0 histogram.

    Collects x0 of every quantity-ish word in the data band (x0 >= _DATA_X0_MIN,
    x0 < _DAYS_X0_MIN) and snaps each of the four default anchors to the modal x0
    within its tolerance window. Falls back to the default if a band is empty.
    """
    xs = []
    for row in pages_rows:
        for w in row:
            if w["x0"] >= _DATA_X0_MIN and w["x0"] < _DAYS_X0_MIN and (
                w["text"] == "-" or _is_num(w["text"])
            ):
                xs.append(w["x0"])
    anchors = dict(_DEFAULT_ANCHORS)
    for key, default in _DEFAULT_ANCHORS.items():
        near = [x for x in xs if abs(x - default) <= _ANCHOR_TOL]
        if near:
            anchors[key] = sum(near) / len(near)
    return anchors


def _bucket(w_x0, anchors):
    """Return the anchor key nearest w_x0 within tolerance, else None."""
    best, bestd = None, _ANCHOR_TOL + 1
    for key, ax in anchors.items():
        d = abs(ax - w_x0)
        if d < bestd:
            best, bestd = key, d
    return best if bestd <= _ANCHOR_TOL else None


def _is_group_total(line_low):
    # Per-division "Values: <DIV> ..." lines AND the un-colon'd grand-total
    # "Values 73,489 ..." line at the end of the report are money totals, skip both.
    return line_low.startswith("values")


def _is_band_header(row):
    """A division band header: all-caps words ending in 'DIV', no numeric cells."""
    toks = [w["text"] for w in row]
    if not toks:
        return False
    if any(_is_num(t) for t in toks):
        return False
    return toks[-1] == "DIV"


_SKIP_STARTS = (
    "item name", "opg", "days last", "on ", "stock n sales", "asha agencies",
    "gstin", "licno", "bilaspur", "email:", "phone:", "to:", "tue,", "piyush",
    "s/w support", "thanking you", "for,", "inw qty", "opg qty",
)


def _strip_leading_serial(row):
    """Drop the leading row-serial word (or glued 'NNName') from the name tokens.

    Serials are the small integers at x0 ~= 35 in the left margin. Some rows glue
    the serial onto the first name word ("10IMXIA", "14SOFIDEW"); strip a leading
    digit run in that case.
    """
    out = []
    for i, w in enumerate(row):
        t = w["text"]
        if i == 0:
            if t.isdigit():
                continue  # bare serial word
            m = re.match(r"^(\d+)(?=[A-Za-z])", t)
            if m:
                t = t[m.end():]
        out.append((t, w))
    return out


def parse_asha_stock_n_sales_status(text, file_bytes=None):
    if not file_bytes:
        return []

    records = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        all_rows = []
        for page in pdf.pages:
            all_rows.extend(_cluster_rows(page))

        anchors = _derive_anchors(all_rows)
        division = None

        for row in all_rows:
            line = " ".join(w["text"] for w in row).strip()
            line_low = line.lower()

            if _is_group_total(line_low):
                continue
            if _is_band_header(row):
                division = " ".join(w["text"] for w in row).strip()
                continue
            if any(line_low.startswith(p) for p in _SKIP_STARTS):
                continue

            # Split words into name/pack (left of data band) and numeric cells.
            named = _strip_leading_serial(row)

            col = {}
            recovered_opening = None
            name_pack_toks = []
            for t, w in named:
                if w["x0"] >= _DATA_X0_MIN:
                    if w["x0"] >= _DAYS_X0_MIN:
                        continue  # Days Last Sale column -> drop
                    if t == "-":
                        continue  # nil cell
                    if _is_num(t):
                        key = _bucket(w["x0"], anchors)
                        if key is not None:
                            col[key] = _to_f(t)
                    continue
                # Word starts in name/pack area. Detect the "ML1" glue: a word whose
                # right edge crosses into the Opg band and ends in a digit run.
                if (
                    w["x1"] >= anchors["opening_stock"] - _ANCHOR_TOL
                    and w["x1"] < anchors["purchase_stock"] - _ANCHOR_TOL
                    and re.search(r"[A-Za-z]", t)
                ):
                    m = _GLUE_TAIL_RE.match(t)
                    if m:
                        recovered_opening = _to_f(m.group("digits"))
                        name_pack_toks.append(m.group("head"))
                        continue
                name_pack_toks.append(t)

            if recovered_opening is not None and "opening_stock" not in col:
                col["opening_stock"] = recovered_opening

            name_pack = " ".join(name_pack_toks).strip(" ,")
            if not name_pack or not col:
                continue

            # Split product name from pack at the first comma (report writes
            # "PRODUCT NAME, PACK"); fall back to whole string as name.
            if "," in name_pack:
                idx = name_pack.rindex(",")
                product = name_pack[:idx].strip()
                pack = name_pack[idx + 1:].strip()
            else:
                product, pack = name_pack, ""

            rec = {
                "product_name": product,
                "pack": pack,
                "division": division,
                "opening_stock": col.get("opening_stock", 0.0),
                "purchase_stock": col.get("purchase_stock", 0.0),
                "sales_qty": col.get("sales_qty", 0.0),
                "closing_stock": col.get("closing_stock", 0.0),
            }
            # Drop fully-empty rows (every quantity cell was a dash).
            if not any(
                rec[k] for k in
                ("opening_stock", "purchase_stock", "sales_qty", "closing_stock")
            ):
                continue
            records.append(rec)

    return records
