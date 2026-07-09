import math

import pandas as pd

from .canonical import CANONICAL_FIELDS, numeric_fields, required_fields


def _present(value):
    if value is None:
        return False
    if isinstance(value, float) and math.isnan(value):
        return False
    return str(value).strip() != ""


def coverage(result, report_type):
    detected = result.get("headers_detected", {}) or {}
    matched_by_field = {}
    for source, canonical_key in detected.items():
        if canonical_key and canonical_key not in matched_by_field:
            matched_by_field[canonical_key] = source

    rows = result.get("rows", []) or []
    chips = []
    for field in required_fields(report_type):
        matched_source = matched_by_field.get(field)
        has_values = any(_present(row.get(field)) for row in rows)
        status = "ok" if matched_source or has_values else "missing"
        if matched_source and not has_values and CANONICAL_FIELDS[report_type][field]["scope"] != "header":
            status = "warn"
        chips.append({"field": field, "status": status, "source_header": matched_source})
    return chips


def _required_detected_points(result, report_type):
    chips = coverage(result, report_type)
    if not chips:
        return 0.0
    found = sum(1 for chip in chips if chip["status"] in {"ok", "warn"})
    return 4.0 * found / len(chips)


def _row_count_points(result, manual_count):
    if not manual_count:
        return 0.0
    actual = len(result.get("rows", []) or [])
    return 2.0 if abs(actual - manual_count) <= max(1, manual_count * 0.02) else 0.0


def _numeric_points(result, report_type):
    rows = result.get("rows", []) or []
    required_nums = numeric_fields(report_type, required_only=True)
    if not rows or not required_nums:
        return 0.0
    total = 0
    valid = 0
    for field in required_nums:
        for row in rows:
            value = row.get(field)
            if not _present(value):
                total += 1
                continue
            total += 1
            if pd.notna(pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]):
                valid += 1
    return 2.0 if total and valid == total else 2.0 * valid / total if total else 0.0


def _quality_points(result, report_type):
    rows = result.get("rows", []) or []
    if report_type == "party":
        if not rows:
            return 0.0
        filled = sum(1 for row in rows if _present(row.get("party_name")))
        return 2.0 if filled == len(rows) else 2.0 * filled / len(rows)
    sanity = result.get("sanity", {}) or {}
    if "pass_rate" in sanity:
        return 2.0 if sanity["pass_rate"] >= 0.98 else 2.0 * max(0.0, sanity["pass_rate"])
    warnings = [w.lower() for w in result.get("warnings", []) or []]
    sanity_warnings = [w for w in warnings if "sanity" in w or "closing" in w]
    return 0.0 if sanity_warnings else 2.0


def score_upload(result, report_type, manual_count=None):
    parts = {
        "required_fields": _required_detected_points(result, report_type),
        "row_count": _row_count_points(result, manual_count),
        "numeric_parse": _numeric_points(result, report_type),
        "quality_check": _quality_points(result, report_type),
    }
    return {"score": round(sum(parts.values()), 2), "max_score": 10, "parts": {k: round(v, 2) for k, v in parts.items()}}
