"""Pluggable recognizers for report-printed control totals.

report_total_reconcile (core/triage.py) scans for label-marked total lines
("Grand Total", "Total :", ...). Whole report families print their controls
WITHOUT any such label and were invisible to it — the 2026-07-21 incident:
a Marg register missing 386 rows (598k of amount) still triaged GREEN because
its printed controls are the per-MF doc-type summaries ("1. Invoice 1669 365
0.00 476336.46") and a bare-numeric grand line ("23171. 4657. -4911.27
3779318.97"), matched by nothing.

This module recognizes those shapes and returns candidate grand totals. It is
consulted ONLY on report_total_reconcile's "no printed total found" exit, so
every file that reconciles via a labelled total today is byte-for-byte
unaffected; the only possible movement is found:False -> found:True.
"""
import re

# Marg per-MF doc-type summary: "N. <DocType> <qty> <free> <disc> <amount>".
# Repeats on every page of its MF section -> dedupe by exact stripped text
# (distinct MFs always differ in their figures).
_MF_DOC_RE = re.compile(
    r"^\s*\d+\.\s+(invoice|credit\s*note|debit\s*note|cash\s*memo|challan|"
    r"s\.?\s*return|sales\s*return)\s+"
    r"(-?[\d,]+)\s+(-?[\d,]+)\s+(-?[\d,]+(?:\.\d{1,2})?)\s+(-?[\d,]+\.\d{2})\s*$",
    re.I,
)

# Bare-numeric total line: digits/punctuation only, >=3 numeric tokens
# ("23171. 4657. -4911.27 3779318.97").
_BARE_LINE_RE = re.compile(r"^[\s\d.,()*%-]+$")
_NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*")


def _f(tok):
    try:
        return float(tok.replace(",", ""))
    except ValueError:
        return None


def _marg_mf_summary(raw_text):
    seen = {}
    for line in raw_text.splitlines():
        s = line.strip()
        m = _MF_DOC_RE.match(s)
        if m and s not in seen:
            seen[s] = (_f(m.group(2)), _f(m.group(3)), _f(m.group(5)))
    if not seen:
        return None
    vals = [v for v in seen.values() if None not in v]
    if not vals:
        return None
    return {
        "kind": "marg_mf_summary",
        "qty": round(sum(v[0] for v in vals), 2),
        "free": round(sum(v[1] for v in vals), 2),
        "amount": round(sum(v[2] for v in vals), 2),
        "lines": len(vals),
        "confidence": "high",
    }


def _bare_numeric_grand(raw_text):
    """Self-validating: among the distinct bare-numeric lines, the grand line's
    LAST number equals the sum of the other lines' last numbers (each per-MF
    tail's amount rolls up into the grand)."""
    cands = []
    seen = set()
    for line in raw_text.splitlines():
        s = line.strip()
        if not s or s in seen or not _BARE_LINE_RE.fullmatch(s):
            continue
        nums = [_f(t) for t in _NUM_RE.findall(s)]
        nums = [x for x in nums if x is not None]
        if len(nums) >= 3:
            seen.add(s)
            cands.append(nums)
    if len(cands) < 3:
        return None
    for i, cand in enumerate(cands):
        others_last = sum(c[-1] for j, c in enumerate(cands) if j != i)
        target = cand[-1]
        if target and abs(others_last - target) <= max(0.01 * abs(target), 0.51):
            return {
                "kind": "bare_numeric_grand",
                "qty": round(cand[0], 2),
                "amount": round(target, 2),
                "lines": len(cands),
                "confidence": "high",
            }
    return None


_RECOGNIZERS = (_marg_mf_summary, _bare_numeric_grand)


def recognize_printed_totals(raw_text, report_type):
    """All recognizer hits, strongest first. Empty list when nothing matches."""
    out = []
    if not raw_text:
        return out
    for rec in _RECOGNIZERS:
        try:
            hit = rec(raw_text)
        except Exception:  # a recognizer must never break triage
            hit = None
        if hit:
            out.append(hit)
    return out
