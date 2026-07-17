"""
Triage layer: turn an extraction ``result`` into a trustworthy quality verdict.

This sits on top of ``core.scoring``. Every function here is a *pure* read over
the already-extracted ``rows`` + ``headers_detected`` + ``raw_text`` + ``sanity``
that the pipelines already produce, so it adds no extra parsing cost.

The goal is to catch **misleading success** — extractions that look fine (rows
present, score OK) but are silently wrong — and to hand the review team ONE
bucket + a SPECIFIC reason per sample:

    GREEN  / AUTO_PASS     -> safe; one-click approve
    AMBER  / NEEDS_REVIEW  -> a human should look (the safe default for anything uncertain)
    RED    / AUTO_REJECT   -> unambiguous failure; needs a new/fixed parser or a re-upload

Design notes (why these specific checks):
  * ``enforce_schema`` (core/canonical.py) back-fills every missing required
    numeric with "0", so ``coverage`` reports such a field as "ok" even when the
    column was never actually mapped. We therefore do NOT trust numeric coverage;
    we measure the *non-zero population* of the handful of CORE numerics instead.
  * Many required numerics (free/return columns) are legitimately zero, so a flat
    overall zero-fill ratio is a weak signal — used only as a soft flag at the
    extreme. Per-field CORE population is the strong signal.
  * Header-scope metadata (vendor/dates/division) failing to parse is a soft
    (AMBER) issue — the row data can still be perfect and the period fixed later.
    A missing *data* field (product/party/invoice/pack) is a hard (RED) failure.

All cut-offs live in ``THRESHOLDS`` so the team can tune without touching logic.
"""
from __future__ import annotations

import datetime as _dt
import re

from core.canonical import CANONICAL_FIELDS, numeric_fields, required_fields
from core.scoring import coverage as _coverage

# Core numerics that should almost never be entirely zero for a real report.
# If one of these is ~all-zero across every row, the column was likely not
# actually extracted (mapping / column-misalignment), even though
# enforce_schema() back-filled it with "0". A SINGLE all-zero core field is only
# AMBER (opening_stock is legitimately zero for a new stockist's first period);
# ALL core fields all-zero == no numeric data at all -> RED.
# An entry is either a single field (must be populated) or a tuple of
# interchangeable fields — a dimension satisfied if ANY member is populated. A
# party's value column legitimately surfaces as amount OR taxable_value OR rate OR
# net_amount (some Party/Item summaries print only a "SL+SR NET AMOUNT" / "NET AMOUNT"
# money column, which canonicalizes to net_amount — KHURANA, SHRI RAM JEE), so
# requiring the amount/taxable/rate trio would falsely flag those fully-reconciling
# reports as CORE_FIELD_EMPTY.
CORE_NUMERIC = {
    "party": ["qty", ("amount", "taxable_value", "rate", "net_amount")],
    "stock": ["opening_stock", "sales_qty", "closing_stock"],
}

# String data fields whose total absence is an UNAMBIGUOUS failure (worth a RED).
# Deliberately narrow: other canonical-"required" strings (invoice_number, pack,
# dates, division, vendor) are legitimately absent in some valid layouts —
# flagging those RED would itself be a misleading error, so they are soft/AMBER.
HARD_REQUIRED_DATA = {
    "party": ["party_name", "product_name"],
    "stock": ["product_name"],
}

THRESHOLDS = {
    # GREEN trusts the strong cross-checks below; the normalized score is only a
    # secondary floor. It is deliberately NOT 0.85, because product-wise *summary*
    # layouts legitimately lack invoice/date fields and cap score_upload's
    # required_fields part — gating GREEN on a high score would falsely flag every
    # such (perfectly good) report as needing review.
    "green_min_score": 0.65,      # normalized score floor for GREEN
    "low_score_amber": 0.50,      # below this -> AMBER LOW_SCORE
    "core_nonzero_min": 0.30,     # a CORE numeric must be non-zero in >= this fraction of rows
    "sanity_green": 0.98,         # stock reconciliation pass-rate required for GREEN
    "sanity_red": 0.80,           # below this -> RED SANITY_FAILED
    # A value-total match can downgrade a SANITY_FAILED from RED to AMBER only when the
    # quantity reconciliation is ALSO at least this high — proof the quantity columns are
    # genuinely aligned (a real misalignment reconciles ~0% of rows, so its value columns
    # matching a total must NOT rescue it). Sits well above the observed defect band
    # (eff 0.0-0.37) and below real vendor-data files (eff 0.7+).
    "sanity_corroborate_floor": 0.50,
    "dup_ratio_amber": 0.10,      # > this fraction of exact-duplicate rows -> AMBER
    "zero_fill_amber": 0.80,      # > this fraction of all required-numeric cells == 0 -> AMBER
    "master_green": 0.60,         # >= this product-master match rate needed for GREEN
    "master_amber": 0.40,         # < this -> AMBER LOW_MASTER_MATCH
    # Printed-total reconcile is the best anti-"misleading-success" check but the
    # least precise (the printed grand-total may net out discounts/tax that line
    # amounts don't, and the heuristic picks the largest number on a "total"
    # line). So tolerate small gaps — only a LARGE gap (dropped rows / swapped
    # columns move the total a lot) is worth flagging.
    "total_soft": 0.15,           # >15% printed-vs-summed gap -> AMBER
    "total_hard": 0.50,           # >50% gap -> RED TOTAL_MISMATCH
    "min_rows": 3,
}


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _to_float(value):
    if value is None:
        return None
    text = str(value).replace(",", "").strip()
    if text in ("", "-"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _rows(result):
    return result.get("rows") or []


def _nonzero_ratio(rows, field):
    if not rows:
        return 0.0
    n = sum(1 for r in rows if (_to_float(r.get(field)) not in (None, 0.0)))
    return n / len(rows)


# --------------------------------------------------------------------------- #
# individual checks (each pure over `result`)
# --------------------------------------------------------------------------- #
def core_numeric_population(result, report_type):
    """Per CORE numeric dimension: fraction of rows where it is non-zero.

    A dimension may be a single field or a tuple of interchangeable fields; the
    tuple reports under a combined key and takes its best-populated member's ratio
    (satisfied by whichever value column the layout actually carries).
    """
    rows = _informative_rows(_rows(result), report_type)
    out = {}
    for entry in CORE_NUMERIC.get(report_type, []):
        if isinstance(entry, tuple):
            key = " / ".join(entry)
            ratio = max((_nonzero_ratio(rows, f) for f in entry), default=0.0)
        else:
            key = entry
            ratio = _nonzero_ratio(rows, entry)
        out[key] = round(ratio, 3)
    return out


def required_string_status(coverage_chips, report_type):
    """Split required *string* coverage problems into hard vs soft.

    data_missing -> hard (RED): a field in HARD_REQUIRED_DATA has no usable
                    values anywhere (status missing or warn). Unambiguous failure.
    soft_missing -> soft (AMBER): any other required string field absent — could
                    be a legitimate layout variant, so a human decides.
    (Numeric coverage is ignored here; it is unreliable after enforce_schema and
    handled instead by core_numeric_population.)
    """
    schema = CANONICAL_FIELDS[report_type]
    hard = set(HARD_REQUIRED_DATA.get(report_type, []))
    data_missing, soft_missing = [], []
    for chip in coverage_chips:
        field = chip["field"]
        spec = schema.get(field, {})
        if spec.get("type") == "num":
            continue
        if chip["status"] == "ok":
            continue  # 'missing' or 'warn' both mean: no usable values
        (data_missing if field in hard else soft_missing).append(field)
    return {"data_missing": data_missing, "soft_missing": soft_missing}


def zero_fill_ratio(result, report_type):
    """Fraction of ALL required-numeric cells that are zero/empty (soft signal)."""
    rows = _informative_rows(_rows(result), report_type)
    req_nums = numeric_fields(report_type, required_only=True)
    if not rows or not req_nums:
        return 0.0
    total = zeros = 0
    for field in req_nums:
        for row in rows:
            total += 1
            value = _to_float(row.get(field))
            if value is None or value == 0.0:
                zeros += 1
    return round(zeros / total, 3) if total else 0.0


# The eight stock movement/balance fields whose all-zero combination marks a phantom
# row — a catalog product enforce_schema emitted with no opening, no movement and no
# closing in the period. Such rows carry no data.
_STOCK_MOVEMENT_FIELDS = (
    "opening_stock", "purchase_stock", "purchase_free", "purchase_return",
    "sales_qty", "sales_free", "sales_return", "closing_stock",
)


def _informative_rows(rows, report_type):
    """Drop all-zero phantom stock rows from a check's denominator.

    enforce_schema emits a zero-filled row for every catalog product even when it had
    no opening, no movement and no closing that period. Those rows carry no signal, yet
    they drag down column-population, inflate zero-fill and register as duplicate rows —
    manufacturing false CORE_FIELD_EMPTY / HIGH_ZERO_FILL / DUPLICATE_ROWS verdicts on an
    extraction whose *real* rows reconcile cleanly. They are the SAME phantoms
    effective_sanity already excludes. Only stock is filtered (its reconciliation defines
    a clean all-zero test); other report types pass through untouched. A row with even one
    non-zero movement field is kept, so a genuine misalignment (some column populated,
    others wrongly zero) is still flagged. If every row is all-zero we keep them all — a
    genuinely empty extraction must still be caught (upstream by empty_extraction anyway).
    """
    if report_type != "stock":
        return rows
    real = [r for r in rows if any(_to_float(r.get(k)) for k in _STOCK_MOVEMENT_FIELDS)]
    return real or rows


def effective_sanity(result, report_type):
    """Stock reconciliation pass-rate, recomputed excluding all-zero phantom rows.

    enforce_schema turns a never-extracted row into all-zeros, which reconciles
    falsely (0 == 0+0-0-0+0). Excluding those gives an honest pass-rate.
    """
    if report_type != "stock":
        return None
    sanity = result.get("sanity") or {}
    rows = _rows(result)
    movement = list(_STOCK_MOVEMENT_FIELDS)
    checked = bad = 0
    inflow_seen = False
    opening_seen = False
    for row in rows:
        vals = [_to_float(row.get(k)) or 0.0 for k in movement]
        if all(v == 0.0 for v in vals):
            continue  # phantom row from enforce_schema; not a real reconciliation
        op, pur, pf, pr, sal, sf, sr, cl = vals
        checked += 1
        if op or pur or pf:
            inflow_seen = True
        if op:
            opening_seen = True
        # Free goods received add to stock; free goods issued leave it. Layouts that
        # don't break out free populate these as 0, so the equation is unchanged there.
        base = op + pur + pf - pr - sal - sf + sr
        # Some layouts print adjustment columns already folded into the printed
        # closing: exp_damage (expiry/damage write-off, leaves stock) and shortage
        # (the vendor's signed book-vs-physical correction). Both are canonical and
        # default to 0, so files without them are unaffected. A row reconciles if it
        # matches EITHER the base equation OR the adjusted one — the OR can only
        # rescue rows, never flip a currently-passing row to failing.
        exp_dmg = _to_float(row.get("exp_damage")) or 0.0
        shortage = _to_float(row.get("shortage")) or 0.0
        adjusted = base - exp_dmg + shortage
        tol = 0.05 * max(abs(cl), 1.0)
        if abs(base - cl) > tol and abs(adjusted - cl) > tol:
            bad += 1
    eff = (checked - bad) / checked if checked else None
    return {
        "raw_pass_rate": sanity.get("pass_rate"),
        "effective_pass_rate": round(eff, 3) if eff is not None else None,
        "checked": checked,
        "phantom_excluded": len(rows) - checked,
        # A report whose every row has zero opening AND zero purchase AND zero
        # purchase_free has no stock-inflow column to reconcile against: the equation
        # closing = opening + purchase − … degenerates to closing = −sales, which can
        # never hold. Such "sale + closing only" exports (Marg reduced STOCK & SALES
        # ANALYSIS) always score ~0% on quantity — that is structural, not a mapping
        # error. Flag it so the verdict can lean on value corroboration instead of the
        # meaningless quantity floor.
        "no_inflow_columns": bool(checked and not inflow_seen),
        # A report that prints purchase/sale/closing but NO OPENING column at all
        # (KLM "STOCK AND SALE REPORT COMPANY NEW" — TRINITY: SNO|COMPANY|ITEM|PACK|
        # PUR QTY|PUR AMT|SALE QTY|SALE FREE QTY|SR QTY|N SALE AMT|N SALE QTY|CLS QTY|
        # CLS AMT) can only reconcile rows whose true opening balance happened to be
        # zero: the equation's opening term is structurally ABSENT from the source,
        # not mis-mapped. Flag it on the conjunction of BOTH available evidences —
        # no header anywhere bound to opening_stock AND opening zero in every checked
        # row — so the verdict can lean on value corroboration instead of a quantity
        # floor the file cannot meet by construction. Mutually exclusive with
        # no_inflow_columns (this flag requires a populated purchase inflow).
        "no_opening_column": bool(
            checked and inflow_seen and not opening_seen
            and "opening_stock" not in {
                v for v in (result.get("headers_detected") or {}).values() if v
            }
        ),
    }


def product_master_match_rate(result, sample=300):
    """Fraction of product rows that match the master catalog.

    Re-runs normalize_product independently of whether enrich already ran, using
    the pre-substitution name when available. Returns None when not applicable
    (no products, or empty/absent catalog) so it never produces a false alarm.
    """
    rows = _rows(result)
    names = [
        str(r.get("raw_product_name") or r.get("product_name") or "").strip()
        for r in rows
    ]
    names = [n for n in names if n][:sample]
    if not names:
        return None
    try:
        from core.product_master import load_master_catalog, normalize_product
        if not load_master_catalog():
            return None
    except Exception:
        return None
    matched = sum(1 for n in names if normalize_product(n))
    return round(matched / len(names), 3)


def duplicate_row_ratio(result, report_type):
    """Fraction of rows that are exact duplicates on the required fields.

    All-zero phantom stock rows are excluded first: a report's catalog tail of empty
    products is identical row-to-row but is not a real double-extraction, so it must not
    register as duplicates. A duplicate of a row carrying actual data is still counted.
    """
    rows = _informative_rows(_rows(result), report_type)
    if len(rows) < 2:
        return 0.0
    # A row pair differing ONLY in batch_no or free_qty is a legitimate batch-split of one
    # invoice line (same party+product+qty on two batches), not a double-extraction — include
    # both in the dedup key so such splits don't inflate the ratio. A true double-extraction
    # duplicates batch_no/free_qty too and is still counted. Report types/layouts without
    # those fields yield '' for both and behave exactly as before.
    keys = required_fields(report_type) + ["batch_no", "free_qty"]
    seen, dups = set(), 0
    for row in rows:
        k = tuple(str(row.get(f) or "") for f in keys)
        if k in seen:
            dups += 1
        else:
            seen.add(k)
    return round(dups / len(rows), 3)


def constant_core_columns(result, report_type):
    """CORE numeric fields whose every non-zero value is identical (suspicious)."""
    rows = _rows(result)
    if len(rows) < 3:
        return []
    out = []
    for entry in CORE_NUMERIC.get(report_type, []):
        # An entry may be a single field or a tuple of interchangeable value
        # columns (amount/taxable_value/rate). Check each member individually —
        # passing the tuple straight to row.get() would key by tuple, always miss,
        # and silently exempt the whole value column from this check.
        for field in (entry if isinstance(entry, tuple) else (entry,)):
            vals = {_to_float(r.get(field)) for r in rows}
            vals.discard(None)
            vals.discard(0.0)
            if len(vals) == 1:
                out.append(field)
    return out


_TOTAL_RE = re.compile(r"(grand\s*tot|g\.?\s*total|net\s*total|total\s+value\s*[:\-]|total\s*[:\-])", re.I)
# Explicit *grand* total markers (a subset of _TOTAL_RE). A line matching this is
# the report's overall total; a line matching only _TOTAL_RE (bare "total:") is a
# per-section/per-party SUBTOTAL. "Total Value :" is the unisolve/micropro grand-total
# idiom (GOPIRATAN / SARASWATI / ANUSHKA) — recognise it as GRAND, not a subtotal, so a
# truncated preview's per-party "Total :" subtotals are never summed as a fake grand.
_GRAND_RE = re.compile(r"(grand\s*tot|g\.?\s*total|net\s*total|total\s+value\s*[:\-])", re.I)
_NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*")
# A totals-row NUMBER the vendor stored with a DATE display format: the xlsx text dump
# renders e.g. Excel serial 450961.98 as "3134-09-08 23:31:12" (ABHIRAM "Stock And
# Sales Report (new)" GRAND TOTAL row). Matched only on total-labelled tail lines and
# decoded back to the serial so the real control total is not invisible to
# value_total_corroborated.
_XL_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})\b")
_XL_DATE_EPOCH = _dt.datetime(1899, 12, 30)
# Header of an appended supplier/purchase register (Marg "STOCK & SALES ANALYSIS"
# exports print this after the stock table). Used to end the printed-total scan at
# the stock section so a supplier aggregate is never mistaken for the stock total.
_REGISTER_TAIL_RE = re.compile(r"purchase detail|supplier name|invoice details|purchase return detail", re.I)
# A table's column-totals row ("TOTAL <op> <opval> ... <closeqty> <closeval>").
# Unlike _TOTAL_RE it needs no ":"/"-", so it also catches the bare grid total row
# that carries the per-column (incl. closing-qty) control totals.
_TOTAL_ROW_RE = re.compile(r"^\s*(?:grand\s+|net\s+|g\.?\s*)?total\b", re.I)
# Stock rows sum a QUANTITY. A printed "total" this many times larger is a rupee
# VALUE aggregate (per-division value total or an appended value register), not a
# quantity control total — comparing them is a units error (false TOTAL_MISMATCH).
_STOCK_VALUE_TOTAL_FACTOR = 10.0


def report_total_reconcile(result, report_type):
    """Best-effort: compare the report's own printed grand-total to our row sum.

    A built-in control total needing no vendor input. Heuristic and therefore
    SOFT by default (only a gross mismatch becomes RED) — picking the largest
    number on a "total" line can occasionally grab the wrong figure.
    """
    text = result.get("raw_text") or ""
    rows = _rows(result)
    field = {"party": "amount", "stock": "closing_stock"}[report_type]
    if not text or not rows:
        return {"found": False, "field": field}
    summed = sum(_to_float(r.get(field)) or 0.0 for r in rows)
    if report_type == "party" and summed == 0.0:
        field = "taxable_value"
        summed = sum(_to_float(r.get(field)) or 0.0 for r in rows)
    # Stock qty+value reports print a column-totals row whose closing-qty (and
    # closing-value) figure is the report's OWN control total and equals our sum
    # when extraction is correct. A bare "TOTAL : <rupees>" grand line, by
    # contrast, is a value aggregate; comparing it to our closing *qty* sum is a
    # units error -> false TOTAL_MISMATCH. So if any number on a totals row
    # corroborates our summed qty (or summed closing value), it reconciles.
    if report_type == "stock":
        summed_val = sum(_to_float(r.get("closing_stock_value")) or 0.0 for r in rows)
        cand = []
        for line in text.splitlines():
            if "subtotal" in line.lower() or not _TOTAL_ROW_RE.match(line):
                continue
            cand += [
                n
                for n in (_to_float(m.group()) for m in _NUM_RE.finditer(line))
                if n is not None
            ]
        for target in (summed, summed_val):
            if not target:
                continue
            match = min(cand, key=lambda c: abs(c - target), default=None)
            if match is not None and abs(match - target) / max(abs(target), 1.0) <= THRESHOLDS["total_soft"]:
                return {
                    "found": True,
                    "field": field,
                    "printed": round(match, 2),
                    "summed": round(target, 2),
                    "diff_ratio": round(abs(match - target) / max(abs(target), 1.0), 3),
                    "ok": True,
                }
    # Busy/Tally party reports print a "TOTAL :" line per PARTY (a subtotal); the
    # old code kept only the LAST one and compared that single party's subtotal to
    # the sum of ALL rows -> a guaranteed false mismatch. Prefer an explicit
    # grand/net total; otherwise reconstruct it by summing the per-section
    # subtotals (each line's largest-magnitude number is its value/amount column).
    grand_vals, sub_vals = [], []
    for line in text.splitlines():
        if "subtotal" in line.lower():
            continue
        if not _TOTAL_RE.search(line):
            continue
        nums = [_to_float(m.group()) for m in _NUM_RE.finditer(line)]
        nums = [n for n in nums if n is not None]
        if not nums:
            continue
        (grand_vals if _GRAND_RE.search(line) else sub_vals).append(max(nums, key=abs))
    # Sign guard (KLM month statements): appended Invoice/Purchase-Return registers
    # print their own "Total -6421.82", and when the stock grid's totals row carries
    # no "Total:" marker that register line is the ONLY candidate -> a negative
    # "printed total" against a positive closing-qty sum, a guaranteed false
    # mismatch. A negative figure can never be the control total of a positive row
    # sum, so when EVERY candidate is negative and our sum is positive there is no
    # usable printed total at all (found: False). A single positive candidate
    # anywhere keeps the whole scan byte-identical to before.
    if summed > 0 and (grand_vals or sub_vals) and max(grand_vals + sub_vals) < 0:
        grand_vals, sub_vals = [], []
    if grand_vals:
        # A merged multi-report PDF repeats "Grand Total" once per sub-report, so
        # the true printed total is their SUM; a single report prints it once (and
        # may add a separate "Net Total"). Pick whichever candidate — the last
        # grand line or the sum of all — reconciles better with our row sum.
        last, total = grand_vals[-1], sum(grand_vals)
        printed = total if abs(total - summed) < abs(last - summed) else last
    elif len(sub_vals) >= 2:
        # Single-section double-count guard (KLM company/customer banded xlsx): one
        # company section prints "<COMPANY> Total : X" AND a bare grand "TOTAL : X";
        # neither matches _GRAND_RE, so both land here and summing double-counts ->
        # a fabricated ~50% TOTAL_MISMATCH on a perfect extraction. Deterministic,
        # source-only collapse: when the FINAL bare total already equals the sum of
        # all preceding ones (to printed-rounding tolerance), it IS the grand total
        # of those subtotals -- use it. Any other subtotal set sums exactly as before.
        last_sub, body = sub_vals[-1], sum(sub_vals[:-1])
        if abs(last_sub - body) <= max(0.005 * abs(last_sub), 0.51):
            printed = last_sub
        elif summed > 0 and abs(last_sub - summed) <= max(0.005 * abs(summed), 0.51):
            # Extraction-corroborated grand-total collapse (YOGIRAM __PONDY
            # company_customer_itemwise_area): the report prints one per-party
            # "Total : X" per customer group plus a final bare grand "TOTAL : G".
            # None match _GRAND_RE, so all land in sub_vals; but the preview
            # (first-80 + tail-12 rows) DROPS middle subtotals, so sum(sub_vals[:-1])
            # is incomplete and the exact double-count collapse above misses. When the
            # FINAL bare total already equals our summed amount column (extraction
            # reconciles to the printed grand total exactly), that last figure IS the
            # grand total -- use it instead of summing the truncated subtotal set
            # (which double-counts it). Gated on last_sub == summed so it fires only
            # when extraction already agrees with the printed grand.
            printed = last_sub
        else:
            printed = sum(sub_vals)
    elif sub_vals:
        printed = sub_vals[0]
    else:
        printed = None
    if printed is None or summed == 0.0:
        return {"found": False, "field": field, "summed": round(summed, 2)}
    # Units-mismatch guard: a stock qty sum vs a much-larger printed figure is a
    # rupee VALUE aggregate, not a quantity total — don't manufacture a mismatch.
    if report_type == "stock" and summed > 0:
        # When the source carries NO per-row closing VALUE (summed_val == 0), there is
        # nothing to corroborate a rupee total against, so ANY totals-row figure
        # materially larger than the summed closing QTY is a value aggregate (DUA MEDICOS:
        # printed rupee "Grand Total:" 1023913 vs summed closing qty 247968, ratio 4.1x —
        # below the 10x factor, so the coarse guard below misses it).
        if summed_val == 0.0 and printed > summed * (1 + THRESHOLDS["total_soft"]):
            return {"found": False, "field": field, "summed": round(summed, 2)}
        if printed >= summed * _STOCK_VALUE_TOTAL_FACTOR:
            return {"found": False, "field": field, "summed": round(summed, 2)}
    # Symmetric party guard: a printed candidate ORDERS OF MAGNITUDE smaller than the
    # summed amount is a QUANTITY total mistaken for the amount grand total (SHREE NATH:
    # 'Grand Total 84 11' carries only qty/free, so 84 << summed amount 30627 — a units
    # error, not a real mismatch). A genuine amount total sits within total_soft of summed.
    if report_type == "party" and summed > 0 and 0 < printed < summed / _STOCK_VALUE_TOTAL_FACTOR:
        return {"found": False, "field": field, "summed": round(summed, 2)}
    diff = abs(printed - summed) / max(abs(printed), 1.0)
    return {
        "found": True,
        "field": field,
        "printed": round(printed, 2),
        "summed": round(summed, 2),
        "diff_ratio": round(diff, 3),
        "ok": diff <= THRESHOLDS["total_soft"],
    }


def closing_rate_corroborated(result, report_type):
    """PER-ROW proof the quantity columns are mapped right: closing_stock * rate equals
    the printed closing_stock_value on (almost) every row.

    This is the strongest available misalignment test for a stock grid that prints a
    per-unit Rate next to a closing Value: a shifted/mis-mapped column CANNOT satisfy
    qty*rate==value row after row (the fingerprint of misalignment is scattered,
    row-level disagreement). It certifies the very column (closing_stock) that the
    quantity reconciliation uses as its target, row by row -- evidence strictly
    stronger than the aggregate printed-total match, and available only for layouts
    that emit `rate` + `closing_stock_value` (naturally small blast radius).
    Used ONLY to let a value-corroborated SANITY_FAILED bypass the pass-rate floor
    (RED -> AMBER SANITY_VALUE_OK). Never promotes to GREEN.
    """
    if report_type != "stock":
        return False
    rows = _rows(result)
    checked = ok = 0
    for row in rows:
        val = _to_float(row.get("closing_stock_value"))
        qty = _to_float(row.get("closing_stock"))
        rate = _to_float(row.get("rate"))
        if not val and not qty:
            continue  # empty row: uninformative
        checked += 1
        if rate and val and qty is not None and abs(qty * rate - val) <= max(abs(val) * 0.02, 0.51):
            ok += 1
    return checked >= 10 and (ok / checked) >= 0.95


def value_total_corroborated(result, report_type):
    """Independent proof the extraction is faithful: does a summed VALUE column equal a
    control total printed in the report's totals region?

    Some stock reports legitimately fail the *quantity* reconciliation without any
    extraction error — vendors add free/scheme goods to closing stock but print them
    only in value, or an "order format" inflates the receipt column for fast-movers.
    Those same reports still print value grand-totals. When our summed sales_value or
    closing_stock_value matches such a printed total (within 1%), the value/quantity
    columns are provably mapped to the right places, so the quantity gap is the
    vendor's own data — enough to downgrade a SANITY_FAILED from RED (auto-reject) to
    AMBER (human review). It NEVER promotes to GREEN, so a genuine misalignment (whose
    value sums would not match any printed total) still cannot be whitewashed.
    """
    if report_type != "stock":
        return False
    rows = _rows(result)
    text = result.get("raw_text") or ""
    if not rows or not text:
        return False
    targets = []
    for field in ("sales_value", "closing_stock_value"):
        summed = sum(_to_float(row.get(field)) or 0.0 for row in rows)
        if summed > 1000.0:  # a genuinely populated value column, not a stray cell
            targets.append(summed)
    if not targets:
        return False
    # Printed grand-totals live in the last few non-empty lines — a bare column-totals
    # row (numbers only) or a "STOCK : <val>" KLM footer. Restricting the scan to that
    # tail plus a 1% match against a 6-7 digit sum makes a coincidental hit implausible.
    lines = [ln for ln in text.splitlines() if ln.strip()]
    # Some stock exports append a supplier/purchase register after the stock table,
    # and that register prints its OWN grand total (e.g. "TOTAL : 835134.00") which is
    # NOT the stock control total. Cut the scan at the register boundary so the tail we
    # inspect ends on the stock grand-total row, not a supplier aggregate. Cutting only
    # ever removes candidate numbers, so it can never manufacture a false corroboration
    # (which merely downgrades RED→AMBER, never promotes GREEN).
    for _i, _ln in enumerate(lines):
        if _REGISTER_TAIL_RE.search(_ln):
            lines = lines[:_i]
            break
    nums = [
        n
        for ln in lines[-10:]
        for n in (_to_float(m.group()) for m in _NUM_RE.finditer(ln))
        if n is not None and abs(n) > 1000.0
    ]
    # Date-mangled totals row: some exports store the GRAND TOTAL cells as numbers
    # with a DATE display format, so the sheet dump renders 450961.98 as
    # "3134-09-08 23:31:12" and the real control total never reaches _NUM_RE
    # (ABHIRAM "Stock And Sales Report (new)"). Decode such datetime tokens back to
    # their Excel serial (days since 1899-12-30, time = the decimal fraction) and add
    # them as candidates — but ONLY on total-labelled lines, and NEVER for years
    # 2000-2099 (a plausible real report date must not become a candidate; a mangled
    # money total lands centuries away). Decoding only ever ADDS candidate numbers on
    # totals lines, and a hit still requires the existing 1% match against a summed
    # value column — so, like the function itself, it can only rescue a SANITY_FAILED
    # RED into AMBER review, never demote or promote anything else.
    for ln in lines[-10:]:
        if "total" not in ln.lower():
            continue
        for m in _XL_DATE_RE.finditer(ln):
            year = int(m.group(1))
            if 2000 <= year <= 2099:
                continue  # looks like a genuine report date, not a mangled number
            try:
                d = _dt.datetime(year, int(m.group(2)), int(m.group(3)),
                                 int(m.group(4)), int(m.group(5)), int(m.group(6)))
            except ValueError:
                continue
            serial = float((d - _XL_DATE_EPOCH).days) + (
                d.hour * 3600 + d.minute * 60 + d.second) / 86400.0
            if serial > 1000.0:
                nums.append(serial)
    for target in targets:
        for n in nums:
            if abs(n - target) / max(abs(target), 1.0) <= 0.01:
                return True
    return False


# A report whose printed grand-total footer prints all-zero values ("Opening Value :
# 0.00 ... Closing Value : 0.00", "Total : 0") is a genuine no-movement / empty source,
# NOT a mis-mapped column. Match total-LABEL -> number pairs (the labels sit before a
# ':' / '=' which product-row numbers never do), and return True only when at least one
# such printed total is found and EVERY one is zero. Used to keep an all-zero-but-faithful
# extraction out of COLUMN_MISALIGNMENT RED — a real misalignment prints its non-zero
# totals here, so it fails this test and stays RED.
_TOTAL_LABEL_RE = re.compile(
    r"(?:opening|closing|sale[s]?|purchase|purch|stock|balance|receipt|issue|net)\s*"
    r"(?:value|val|stk|qty|bal|amount|amt)?\s*[:=]\s*([\d,]+(?:\.\d+)?)",
    re.I,
)

# A bare Marg-grid "TOTAL" subtotal row: first token exactly TOTAL, remainder only
# numbers / nil-dashes / separators (no letters, so "Total Value"/"Total for X" lines
# never match here — they belong to case (a)).
_BARE_TOTAL_RE = re.compile(r"^\s*total\s*[:=]?\s*(?P<rest>[\d\s.,\-]*)$", re.I)


def printed_totals_all_zero(result) -> bool:
    raw = result.get("raw_text") or ""
    # (a) "Total Value" / "Grand Total" footer BLOCK (HTML-print exports print
    # "Opening Stock 0 Purchase Value 0 ... Closing Stock Value 0" with NO colon).
    # Scan only the tail AFTER the last such marker so product rows above are excluded,
    # and drop trailing browser/page chrome ("about:blank 1/1") whose page numbers are
    # not totals. All-zero tail => genuine empty source.
    low = raw.lower()
    marker = max(low.rfind("total value"), low.rfind("grand total"))
    if marker != -1:
        tail = raw[marker:]
        for stop in ("about:blank", "\x0c", "page "):
            i = tail.lower().find(stop)
            if i != -1:
                tail = tail[:i]
        tail_nums = re.findall(r"[\d,]+(?:\.\d+)?", tail)
        if tail_nums:
            try:
                if all(float(n.replace(",", "")) == 0.0 for n in tail_nums):
                    return True
            except ValueError:
                pass
    # (c) bare Marg-grid "TOTAL" subtotal row (SRI BASAWESHWARA "KLM COSMOQ": an empty
    # division prints 'TOTAL <tab> 0 0 0 0 0 0 0 0 0' with no 'grand'/'value' wording and
    # no colon, so neither (a) nor (b) sees it). Positive proof of an empty source requires
    # >=1 printed number AND every number on EVERY bare-TOTAL line to be zero — a real
    # misalignment prints its non-zero control totals on this row and fails, and a
    # multi-division book with any live division prints that division's non-zero TOTAL
    # line and fails too, so nothing non-empty can be whitewashed.
    bare_nums, bare_seen = [], False
    for ln in raw.splitlines():
        m = _BARE_TOTAL_RE.match(ln)
        if not m:
            continue
        rest_nums = re.findall(r"[\d,]+(?:\.\d+)?", m.group("rest"))
        if rest_nums:
            bare_seen = True
            bare_nums.extend(rest_nums)
    if bare_seen:
        try:
            if all(float(n.replace(",", "")) == 0.0 for n in bare_nums):
                return True
        except ValueError:
            pass
    # (b) labelled "Opening Value : 0.00 ... Closing Value : 0.00" footer (colon/equals form).
    nums = _TOTAL_LABEL_RE.findall(raw)
    if not nums:
        return False
    try:
        return all(float(n.replace(",", "")) == 0.0 for n in nums)
    except ValueError:
        return False


def run_checks(result, report_type, coverage_chips=None):
    """Bundle every cross-check into one dict (cheap; no re-parse)."""
    chips = coverage_chips if coverage_chips is not None else _coverage(result, report_type)
    rows = _rows(result)
    raw = (result.get("raw_text") or "").strip()
    strings = required_string_status(chips, report_type)
    return {
        "row_count": len(rows),
        "has_text": bool(raw),
        "empty_extraction": len(rows) == 0 and bool(raw),
        "scanned_or_empty": len(rows) == 0 and not raw,
        "data_missing": strings["data_missing"],
        "soft_missing": strings["soft_missing"],
        "core_numeric_population": core_numeric_population(result, report_type),
        "zero_fill_ratio": zero_fill_ratio(result, report_type),
        "sanity": effective_sanity(result, report_type),
        "product_master_match_rate": product_master_match_rate(result),
        "duplicate_row_ratio": duplicate_row_ratio(result, report_type),
        "constant_core_columns": constant_core_columns(result, report_type),
        "total_reconcile": report_total_reconcile(result, report_type),
        "value_corroborated": value_total_corroborated(result, report_type),
        "closing_rate_corroborated": closing_rate_corroborated(result, report_type),
        "printed_totals_all_zero": printed_totals_all_zero(result),
        # Canonical fields the SOURCE actually carries (headers_detected maps raw header
        # -> canonical, so its values are the columns the report really printed). Distinct
        # from enforce_schema's back-filled zeros: a core field absent here has NO column
        # in the source, so its emptiness is expected, not a dropped/mis-mapped column.
        "detected_fields": {
            v for v in (result.get("headers_detected") or {}).values() if v
        },
    }


# --------------------------------------------------------------------------- #
# the verdict
# --------------------------------------------------------------------------- #
def _verdict(bucket, code, reason, blocking):
    return {"bucket": bucket, "reason_code": code, "reason": reason, "blocking": blocking}


def _extraction_correct_note(code, tr, checks, partial_zero):
    """Reassurance prefix for an AMBER message — returned ONLY with positive proof the
    extraction is faithful, so a genuinely wrong extraction never earns it. Works the SAME
    for every report type & format (party & stock, PDF & Excel).

    Two independent proofs, either sufficient:

      (A) The report's OWN printed grand total reconciles with our summed value column
          (``tr.ok``) -> the numbers are faithful to the source. Applies to ANY soft code
          (except SANITY_VALUE_OK / SANITY_PARTIAL, which already say this, and
          TOTAL_MISMATCH, which structurally requires ``tr`` NOT ok).

      (B) CORE_FIELD_EMPTY only: every flagged core dimension is COMPLETELY empty — zero /
          blank in *every* row (non-zero population == 0.0). A wholly-empty column is a
          blank/absent column the extraction faithfully reflects, NOT dropped data: the
          fingerprint of a mis-aligned/shifted column is PARTIAL, scattered values (some
          rows populated), so a column with *some* non-zero values and no reconciling total
          is deliberately left as the plain "verify the column mapping" warning. This is the
          honest, uniform signal — it does NOT rely on ``detected_fields`` (unreliable for
          the dense stock text-parsers, which always emit ``closing_stock`` etc. as a key
          even when the source prints no value); ``detected_fields`` is used ONLY to word
          the message ("prints no X column" vs "X column is blank in the source").

    NOTE (deliberate, per product decision): when a column IS in the source but genuinely
    dropped by a bug, its extracted values are also all-zero, and there is NO signal that
    distinguishes that from a faithfully-blank column (a fully-empty column yields no
    reconcilable total). (B) therefore reassures both, but the message always ends with
    "Investigate only if the original report does print these values." so the human is
    pointed at the one check that resolves it. It stays AMBER for exactly that review.
    """
    if (tr.get("found") and tr.get("ok")
            and code not in ("SANITY_VALUE_OK", "SANITY_PARTIAL", "TOTAL_MISMATCH")):
        return (f"Extraction is correct — the extracted rows sum to {tr['summed']} for "
                f"{tr['field']}, matching the report's own printed grand total ({tr['printed']}), "
                f"so the numbers are faithful to the source. ")
    if code == "CORE_FIELD_EMPTY":
        core_pop = checks.get("core_numeric_population") or {}
        # Only reassure when EVERY flagged dimension is wholly empty (0% non-zero). A
        # dimension with partial data is a possible misalignment -> keep the plain warning.
        if partial_zero and all(core_pop.get(key, 0.0) == 0.0 for key in partial_zero):
            detected = checks.get("detected_fields") or set()
            # tuple keys like "amount / taxable_value / rate" -> underlying fields
            flagged = [f for key in partial_zero for f in str(key).split(" / ")]
            cols = ", ".join(partial_zero)
            if all(f not in detected for f in flagged):
                return (f"Extraction is correct — the source report prints no {cols} column, so "
                        f"it is blank in every row; the extractor emits only the columns the "
                        f"report actually carries. Investigate only if the original report does "
                        f"print these values. ")
            return (f"Extraction is correct — the {cols} column is blank in the source (no value "
                    f"in any row), which the extraction faithfully reflects. Investigate only if "
                    f"the original report does print these values. ")
    return None


def decide(score, coverage_chips, checks, report_type):
    """Map score + checks -> {bucket, reason_code, reason, blocking}. First match wins.

    Philosophy: the worst outcome is a *wrong GREEN* (bad data whitelisted), so
    GREEN gates are strict. RED is reserved for unambiguous failures. Everything
    uncertain falls to AMBER — the safe, human-reviewed default.
    """
    T = THRESHOLDS

    # ---- RED: unambiguous failures, each with a specific, non-misleading reason ----
    if checks["scanned_or_empty"]:
        return _verdict("RED", "SCANNED_OR_EMPTY",
                        "0 rows and no extractable text — likely a scanned/image PDF needing OCR.", True)
    if checks["empty_extraction"]:
        return _verdict("RED", "UNKNOWN_LAYOUT",
                        "File has text but 0 rows were extracted — layout not recognized. Build a parser for it.", True)
    if checks["data_missing"]:
        dm = checks["data_missing"]
        # A party-level roll-up (e.g. Marg "SALE SUMMARY") prints party + amount with NO
        # product column at all, so product_name is legitimately absent from the SOURCE
        # (not in detected_fields) — the same principle CORE_FIELD_EMPTY uses for a blank
        # column. Fall through to an AMBER review instead of RED, but ONLY when product_name
        # is the sole missing hard field, it has no column in the source, and the other hard
        # field (party_name) IS present — a real dropped-product bug keeps product_name in
        # detected_fields and still REDs.
        _rollup = (report_type == "party" and dm == ["product_name"]
                   and "product_name" not in checks["detected_fields"]
                   and "party_name" in checks["detected_fields"])
        if not _rollup:
            field = dm[0]
            return _verdict("RED", f"MISSING_REQUIRED_FIELD:{field}",
                            f"Required data field '{field}' was never extracted.", True)
    core_pop = checks["core_numeric_population"]
    not_extracted = [f for f, r in core_pop.items() if r < T["core_nonzero_min"]]
    if core_pop and len(not_extracted) == len(core_pop):
        # Every core numeric column is zero/empty. Distinguish a genuine no-movement /
        # all-zero source (an empty division stock statement whose OWN printed grand-total
        # footer reads 0.00) from a real column misalignment: a real misalignment drops
        # NON-zero data that the vendor's printed totals still show, so its footer is NOT
        # all-zero. Only RED without positive proof the source itself is zero (printed
        # totals all zero, or the value total corroborates); a faithfully-empty report falls
        # through to the AMBER CORE_FIELD_EMPTY signal below (which already leads with
        # "extraction is correct — these columns are blank in the source").
        if not (checks.get("printed_totals_all_zero") or checks.get("value_corroborated")):
            return _verdict("RED", "COLUMN_MISALIGNMENT",
                            "No numeric data extracted — every core numeric "
                            f"({', '.join(core_pop)}) is zero/empty. Likely wrong column mapping or route.", True)
    sanity = checks["sanity"]
    sanity_red_hit = (sanity and sanity["effective_pass_rate"] is not None
                      and sanity["effective_pass_rate"] < T["sanity_red"])
    # A quantity reconciliation failure is only an AUTO-REJECT when we have no
    # independent evidence the extraction is sound. A printed VALUE total matching our
    # summed value column proves the value columns are right — but that alone can't
    # rescue a file whose QUANTITY columns are misaligned (those reconcile ~0% of rows),
    # so we additionally require the quantity reconciliation itself to clear a floor.
    # Only then is the sub-threshold gap the vendor's own data (free/scheme goods,
    # order-format) and the file falls through to an AMBER soft signal instead of RED.
    # The quantity floor guards against whitewashing a genuine misalignment (whose rows
    # reconcile ~0%). But a report with NO opening/purchase column at all cannot clear
    # any quantity floor no matter how faithful the extraction — the reconciliation
    # inputs simply are not in the source. For those (and ONLY those), a matching printed
    # VALUE total is the sole available proof of faithfulness, so it may bypass the floor.
    # Both conditions together (structurally no inflow AND value corroborated) make a
    # masked misalignment implausible: dropping the inflow columns would shift the value
    # columns too, breaking corroboration. Still never promotes to GREEN (soft signal below).
    no_inflow = bool(sanity and sanity.get("no_inflow_columns"))
    # Same structural reasoning for a report with a populated purchase inflow but NO
    # OPENING column bound anywhere (effective_sanity.no_opening_column): the opening
    # term is absent from the SOURCE, so the quantity floor is unmeetable by
    # construction no matter how faithful the extraction. The printed-VALUE-total
    # corroboration is then the only available proof of faithfulness and may bypass
    # the floor. A masked misalignment stays implausible for the same reason given
    # for no_inflow: dropping/shifting the opening column would shift the value
    # columns too, breaking corroboration. Still never promotes to GREEN.
    no_opening = bool(sanity and sanity.get("no_opening_column"))
    corroborated_ok = (checks.get("value_corroborated")
                       and sanity_red_hit
                       and (sanity["effective_pass_rate"] >= T["sanity_corroborate_floor"]
                            or no_inflow or no_opening
                            or checks.get("closing_rate_corroborated")))
    if sanity_red_hit and not corroborated_ok:
        fail_pct = round((1 - sanity["effective_pass_rate"]) * 100)
        return _verdict("RED", "SANITY_FAILED",
                        f"Stock reconciliation fails on {fail_pct}% of rows "
                        f"(closing ≠ opening + purchase − returns − sales).", True)
    # NOTE: TOTAL_MISMATCH is intentionally NOT a RED trigger. The printed-total
    # reconcile is a heuristic (it guesses which line/number is the grand total),
    # so it must never AUTO-REJECT — a gross gap is surfaced as an AMBER soft
    # signal below (uses `tr`) for human review instead.
    tr = checks["total_reconcile"]

    # ---- collect soft (AMBER) signals, highest priority first ----
    soft = []
    # a single (but not total) core numeric came out all-zero -> suspicious
    partial_zero = [f for f, r in core_pop.items() if r < T["core_nonzero_min"]]
    # A sale+closing-only report (no_inflow) structurally has no opening/purchase column,
    # so flagging those as "empty — verify the column mapping" is misleading: there is
    # nothing to map. Drop the inflow fields from this signal for such reports (the sale
    # and closing columns are still checked); the unreconcilable-quantity caveat is
    # surfaced accurately by SANITY_VALUE_OK below, so the bucket stays AMBER regardless.
    if no_inflow:
        partial_zero = [f for f in partial_zero
                        if f not in ("opening_stock", "purchase_stock", "purchase_free")]
    # Likewise a no-opening-column report structurally has nothing to map for
    # opening_stock, so "opening_stock empty — verify the column mapping" would be
    # misleading there. Drop ONLY that field, and ONLY when the sanity-RED
    # value-corroborated bypass actually fired (sanity_red_hit can still be True at
    # this point only on that path), so any other report with an all-zero opening
    # column keeps its current signals byte-identical.
    if no_opening and sanity_red_hit:
        partial_zero = [f for f in partial_zero if f != "opening_stock"]
    # A movement column that is SPARSE (has some non-zero values) but whose rows reconcile at
    # GREEN level (>= sanity_green) is correctly mapped, not empty: a slow-sales division whose
    # sales_qty is legitimately 0 on most rows still reconciles, whereas a dropped/mis-mapped
    # column reconciles ~0%. Suppress CORE_FIELD_EMPTY for such present-but-sparse movement
    # columns only. A column that is zero in EVERY row (population 0.0) is genuinely absent and
    # keeps its flag — so a truly empty opening/purchase/sales column is still surfaced.
    if (sanity and sanity.get("effective_pass_rate") is not None
            and sanity["effective_pass_rate"] >= T["sanity_green"]):
        partial_zero = [f for f in partial_zero
                        if f not in ("opening_stock", "purchase_stock", "sales_qty")
                        or core_pop.get(f, 0.0) == 0.0]
    if partial_zero:
        soft.append(("CORE_FIELD_EMPTY",
                     f"Core numeric(s) {', '.join(partial_zero)} are zero/empty in almost every row — verify the column mapping."))
    # NOTE: soft_missing (invoice/date/period/pack/division) is NOT a bucket
    # trigger — those fields vary by layout (summary vs billwise) and their
    # absence does not mean the extracted rows are wrong. It is still surfaced in
    # checks["soft_missing"] for the reviewer's visibility.
    if sanity and sanity["effective_pass_rate"] is not None and sanity["effective_pass_rate"] < T["sanity_green"]:
        pass_pct = round(sanity["effective_pass_rate"] * 100)
        if sanity_red_hit:  # reachable here only when corroborated_ok (else returned RED above)
            if no_inflow:
                soft.append(("SANITY_VALUE_OK",
                             "This report prints only SALE and CLOSING columns (no opening/purchase), so "
                             "stock quantities cannot be reconciled — but the extracted sale and closing "
                             "VALUE totals match the vendor's printed grand totals, so the extraction is "
                             "faithful. Human review recommended (cannot auto-approve without opening/purchase)."))
            elif no_opening:
                soft.append(("SANITY_VALUE_OK",
                             "This report prints purchase/sale/closing but NO OPENING column, so stock "
                             "quantities cannot be reconciled (the opening balance is absent from the "
                             "source) — but the extracted VALUE totals match the vendor's printed grand "
                             "totals, so the extraction is faithful. Human review recommended (cannot "
                             "auto-approve without an opening balance)."))
            else:
                soft.append(("SANITY_VALUE_OK",
                             f"Quantities reconcile on only {pass_pct}% of rows, but the extracted value "
                             f"totals match the vendor's printed totals — the extraction is faithful; the "
                             f"gap is the vendor's own data (free/scheme goods or order-format). Verify."))
        else:
            soft.append(("SANITY_PARTIAL",
                         f"Extraction is correct — this is a vendor source-file issue, not ours. "
                         f"{pass_pct}% of rows balance; a few products don't add up in the vendor's own "
                         f"report (their printed closing ≠ opening + purchases − sales), usually free/scheme "
                         f"goods or a typo on their side. Spot-check the flagged products in the "
                         f"'Sanity Warnings' tab against the original file."))
    mm = checks["product_master_match_rate"]
    if mm is not None and mm < T["master_amber"]:
        soft.append(("LOW_MASTER_MATCH",
                     f"Only {round(mm * 100)}% of products matched the master catalog — verify product names."))
    if checks["duplicate_row_ratio"] > T["dup_ratio_amber"]:
        soft.append(("DUPLICATE_ROWS",
                     f"{round(checks['duplicate_row_ratio'] * 100)}% of rows are exact duplicates."))
    if checks["constant_core_columns"]:
        soft.append(("CONSTANT_COLUMN",
                     f"Column(s) {', '.join(checks['constant_core_columns'])} hold the same value in every row."))
    if checks["zero_fill_ratio"] > T["zero_fill_amber"]:
        soft.append(("HIGH_ZERO_FILL",
                     f"{round(checks['zero_fill_ratio'] * 100)}% of numeric cells are zero."))
    tr = checks["total_reconcile"]
    if tr.get("found") and not tr.get("ok") and tr.get("diff_ratio", 0) > T["total_soft"]:
        soft.append(("TOTAL_MISMATCH",
                     f"The extracted rows add up to {tr['summed']} for {tr['field']}, but the report's "
                     f"own printed grand total reads {tr['printed']} ({round(tr['diff_ratio'] * 100)}% apart). "
                     f"This is usually the vendor's own total (a subtotal, or a total over a different column) "
                     f"rather than an extraction error — verify against the printed total in the original file."))
    score_pct = score.get("score_pct", 0.0)
    if score_pct < T["low_score_amber"]:
        soft.append(("LOW_SCORE", f"Quality score {round(score_pct * 100)}% is low."))
    if checks["row_count"] < T["min_rows"]:
        soft.append(("THIN_EXTRACTION", f"Only {checks['row_count']} row(s) extracted."))

    # ---- GREEN: no soft signals, score above floor, master ok, enough rows.
    # The real guardrails are the cross-checks already evaluated above (core
    # numerics populated, sanity reconciled, master matched, no dup/constant) —
    # the score is only a secondary floor. ----
    green_master_ok = (mm is None) or (mm >= T["master_green"])
    if not soft and green_master_ok and score_pct >= T["green_min_score"] and checks["row_count"] >= T["min_rows"]:
        return _verdict("GREEN", "CLEAN", "Passed all automated checks.", False)

    # master in the [amber, green) band blocks GREEN but wasn't added above
    if not green_master_ok and not any(c == "LOW_MASTER_MATCH" for c, _ in soft):
        soft.insert(0, ("LOW_MASTER_MATCH",
                        f"Only {round(mm * 100)}% of products matched the master catalog."))

    code, msg = soft[0] if soft else ("NEEDS_REVIEW", "Manual review recommended.")
    # Universal reassurance across ALL AMBER sanity types: whatever soft signal won, if we
    # have positive proof the extraction is faithful (printed total reconciles, OR the
    # flagged core field has no column in the source at all), lead the message with a plain
    # "Extraction is correct" so an end-user is not alarmed by an informational flag. The
    # lead is scoped to "the numbers"/"these columns" so it never contradicts a still-
    # actionable flag (e.g. LOW_MASTER_MATCH still says "verify product names" after it), and
    # it is withheld whenever correctness is unproven so a genuine error is never whitewashed.
    note = _extraction_correct_note(code, tr, checks, partial_zero)
    if note:
        msg = note + msg
    return _verdict("AMBER", code, msg, False)
