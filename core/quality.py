"""
One call that turns an extraction ``result`` into the full quality payload the
service and review tools consume: the existing 0-10 score + per-field coverage +
the cross-checks and triage verdict from ``core.triage``.

Score note: ``score_upload``'s 2-point ``row_count`` part can only be earned when
a manual row count is supplied — which vendors never do at scale. So we also
publish ``score_pct``: the score normalized over the parts that are actually
applicable (row_count excluded when there is no manual count). Triage gates on
``score_pct`` so a perfect extraction isn't permanently capped at 8/10.
"""
from __future__ import annotations

from core.scoring import coverage, score_upload
from core.triage import decide, run_checks

ROW_COUNT_POINTS = 2.0  # weight of the row_count part in score_upload


def build_quality(result, report_type, manual_count=None):
    score = score_upload(result, report_type, manual_count)
    parts = score["parts"]
    applicable_max = score["max_score"]
    if not manual_count:
        applicable_max -= ROW_COUNT_POINTS  # unscorable without a manual count
    score_pct = round(sum(parts.values()) / applicable_max, 3) if applicable_max else 0.0
    score = {**score, "score_pct": score_pct}

    cov = coverage(result, report_type)
    checks = run_checks(result, report_type, cov)
    triage = decide(score, cov, checks, report_type)
    return {
        "score": score["score"],
        "score_pct": score_pct,
        "max_score": score["max_score"],
        "parts": parts,
        "coverage": cov,
        "checks": checks,
        "triage": triage,
    }
