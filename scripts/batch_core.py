#!/usr/bin/env python3
"""
Reusable analysis functions — turn ONE cached extraction result into each phase's
verdict, with no re-parsing. The orchestrator (run_batch.py) calls these over the
shared `batch_extract` cache so triage, header-scan, product-harvest, misfiled
classification and regression metrics all read the SAME extraction.

Every function here is pure over a `result` dict (or plain inputs) and reuses the
EXISTING canonical logic so the orchestrator's output matches the standalone tools:

  * triage_row()        -> mirrors triage_batch.py:triage_one() exactly (core.quality)
  * analyze_unmapped_headers() -> mirrors build_header_synonyms.py's per-file loop
  * harvest_spellings() -> the spelling collection in build_product_synonyms.py
  * match_spellings_to_master() -> build_product_synonyms.py's strict matcher (scan only)
  * classify_misfiled() -> relocate_misfiled_reports.py:classify()
  * regression_metrics() -> regression_test.py:_snapshot() off a cached result

build_product_synonyms and regression_test are safe to import (no import-time side
effects). build_header_synonyms and relocate_misfiled_reports are NOT imported —
they monkeypatch product-master enrichment OFF at import time, which would corrupt
the shared (enriched) extraction; their small logic is reproduced faithfully here.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from core.quality import build_quality
from core.header_match import match_header, normalize
from core.product_master import _normalize_name

# Safe to import (no import-time monkeypatch, no main() side effects):
from regression_test import _party_metrics, _stock_metrics, _completeness_metrics
# NOTE: build_product_synonyms is imported LAZILY inside match_spellings_to_master()
# — it is a PSUI-only catalog CLI, and batch_core is mirrored to Backends/scripts
# (run_full_suite dependency) where that module does not exist.


def report_type(route: str) -> str:
    return "stock" if route.startswith("stock") else "party"


# --------------------------------------------------------------------------- #
# reason-code knowledge — ONE source of truth for plain-English + fix routing.
# Used by both run_batch.py (green-gain estimate) and render_dashboard.py (HTML).
# (plain_english, fix_type, who, severity, code_fixable)
# --------------------------------------------------------------------------- #
REASON_META = {
    "UNKNOWN_LAYOUT":    ("No parser recognises this layout (text present, 0 rows)", "New parser",        "Dev",        "RED",   True),
    "SCANNED_OR_EMPTY":  ("Scanned / image or empty — no text (needs OCR)",          "OCR quarantine",    "OCR track",  "RED",   False),
    "EXTRACTION_CRASHED":("Extractor crashed (corrupt / unreadable file)",           "Review / quarantine","OCR track", "RED",   False),
    "COLUMN_MISALIGNMENT":("Columns misaligned — no numeric data extracted",         "Header-mapping",    "You decide", "RED",   True),
    "CORE_FIELD_EMPTY":  ("A core numeric column is empty in nearly all rows",       "Header-mapping",    "You decide", "AMBER", True),
    "SANITY_FAILED":     ("Stock totals don't reconcile on most rows",               "Diagnose sanity",   "Dev + you",  "RED",   True),
    "SANITY_PARTIAL":    ("Stock totals reconcile on most but not all rows",         "Diagnose sanity",   "Dev + you",  "AMBER", True),
    "SANITY_VALUE_OK":   ("Extraction proven right by value totals; vendor's own quantities don't add up", "Review", "You decide", "AMBER", False),
    "PRODUCT_ROLLUP":    ("Party-level roll-up — source has no product column",      "Review",            "You decide", "AMBER", False),
    "TOTAL_MISMATCH":    ("Printed grand total differs from the summed rows",        "Reconcile / audit", "Dev + you",  "AMBER", True),
    "UNACCOUNTED_LINES": ("Source data lines not matched to any extracted row (possible dropped rows)", "Diagnose parser", "Dev", "AMBER", True),
    "HIGH_ZERO_FILL":    ("Too many zero-filled numeric cells",                      "Case-by-case",      "You decide", "AMBER", True),
    "DUPLICATE_ROWS":    ("High duplicate-row ratio",                                "Case-by-case",      "You decide", "AMBER", True),
    "CONSTANT_COLUMN":   ("A column holds the same value in every row",              "Case-by-case",      "You decide", "AMBER", True),
    "THIN_EXTRACTION":   ("Very few rows extracted",                                 "Case-by-case",      "You decide", "AMBER", True),
    "LOW_SCORE":         ("Low overall quality score",                              "Case-by-case",      "You decide", "AMBER", True),
    "LOW_MASTER_MATCH":  ("Few product names match the master catalog",             "Catalog enrichment","You decide", "AMBER", True),
    "NEEDS_REVIEW":      ("Manual review recommended",                              "Review",            "You decide", "AMBER", True),
    "CLEAN":             ("OK — extracted cleanly",                                 "—",                 "—",          "GREEN", False),
}


def fix_meta(reason_code: str) -> dict:
    """(plain_english, fix_type, who, severity, code_fixable) for any reason code."""
    rc = reason_code or ""
    if rc.startswith("MISSING_REQUIRED_FIELD"):
        field = rc.split(":", 1)[-1] if ":" in rc else "field"
        meta = (f"Required column '{field}' not detected / mapped", "Header-mapping", "You decide", "RED", True)
    else:
        meta = REASON_META.get(rc, (rc or "Unknown", "Review", "You decide", "AMBER", True))
    return {"plain": meta[0], "fix_type": meta[1], "who": meta[2], "severity": meta[3], "code_fixable": meta[4]}


def problem_text(reason_code: str) -> str:
    return fix_meta(reason_code)["plain"]


def _completeness_fields(result: dict, checks: dict) -> dict:
    """Line-ledger + printed-total fields for the rows-completeness gate.

    Derived from the SAME build_quality pass as the triage verdict (checks
    carries total_reconcile), so run_full_suite's S4 costs nothing extra.
    would_fire mirrors scripts/ledger_league.would_fire: the ledger thresholds
    AND NOT printed-total-proven (a file whose sums equal the vendor's own grand
    total is complete; unexplained lines there are ledger noise, not drops).
    """
    from core.triage import THRESHOLDS
    la = result.get("line_audit") or {}
    c = la.get("counts") or {}
    tr = checks.get("total_reconcile") or {}
    total_proven = bool(tr.get("found") and tr.get("ok"))
    would_fire = bool(
        not total_proven
        and la.get("applicable")
        and c.get("data", 0) >= THRESHOLDS["unaccounted_min_data"]
        and c.get("unexplained", 0) >= THRESHOLDS["unaccounted_min_lines"]
        and (la.get("unexplained_ratio") or 0.0) >= THRESHOLDS["unaccounted_ratio"]
    )
    return {
        "line_applicable": bool(la.get("applicable")),
        "line_unexplained": c.get("unexplained"),
        "line_data": c.get("data"),
        "total_proven": total_proven,
        "ledger_would_fire": would_fire,
    }


# --------------------------------------------------------------------------- #
# 1. triage  — identical shape & logic to triage_batch.py:triage_one()
# --------------------------------------------------------------------------- #
def triage_row(route: str, vendor: str, file_name: str, path: str, result: dict) -> dict:
    base = {"vendor": vendor, "file_name": file_name, "route": route, "path": path}
    err = result.get("_extract_error") if isinstance(result, dict) else None
    if err:
        return {
            **base, "layout": "ERROR", "bucket": "ERROR",
            "reason_code": "EXTRACTION_CRASHED", "reason": err,
            "extraction_ok": False,
            "score_pct": None, "row_count": None, "sanity_eff": None,
            "master_match": None, "dup_ratio": None, "zero_fill": None,
            "soft_missing": "", "warnings": None,
        }
    try:
        quality = build_quality(result, report_type(route))
        debug = result.get("debug") or {}
        checks = quality["checks"]
        triage = quality["triage"]
        sanity = checks.get("sanity") or {}
        return {
            **base,
            "layout": debug.get("layout") or debug.get("detected_format") or "unknown",
            "bucket": triage["bucket"],
            "reason_code": triage["reason_code"],
            "reason": triage["reason"],
            # 4-state triage badge (GREEN/AMBER-true/AMBER-null/RED) rides on this;
            # True=proven correct, None=unconfirmed AMBER, False=RED. See core/triage.py:_verdict.
            "extraction_ok": triage.get("extraction_ok"),
            "score_pct": quality["score_pct"],
            "row_count": checks["row_count"],
            "sanity_eff": sanity.get("effective_pass_rate"),
            "master_match": checks.get("product_master_match_rate"),
            "dup_ratio": checks.get("duplicate_row_ratio"),
            "zero_fill": checks.get("zero_fill_ratio"),
            "soft_missing": ", ".join(checks.get("soft_missing") or []),
            "warnings": len(result.get("warnings") or []),
            # Line-ledger completeness + printed-total proof (run_full_suite's S4
            # rows gate reads these; additive — dashboards ignore extra keys).
            # Exposed here so the suite derives triage AND completeness from this
            # ONE build_quality pass instead of re-running the catalog fuzzy-match.
            **_completeness_fields(result, checks),
        }
    except Exception as exc:  # mirror triage_one's defensive catch
        return {
            **base, "layout": "ERROR", "bucket": "ERROR",
            "reason_code": "EXTRACTION_CRASHED", "reason": f"{type(exc).__name__}: {exc}",
            "extraction_ok": False,
            "score_pct": None, "row_count": None, "sanity_eff": None,
            "master_match": None, "dup_ratio": None, "zero_fill": None,
            "soft_missing": "", "warnings": None,
        }


# --------------------------------------------------------------------------- #
# 2. unmapped headers  — mirrors build_header_synonyms.py main loop, per file
# --------------------------------------------------------------------------- #
def analyze_unmapped_headers(result: dict, rtype: str, min_score: float = 0.62) -> list[dict]:
    """Return the headers in this file that map to NO canonical field.

    Each item: {header, norm, guess, score}. Same matcher as the header scanner.
    """
    out: list[dict] = []
    for source_header in (result.get("headers_detected") or {}):
        header = str(source_header).strip()
        norm = normalize(header)
        if not norm:
            continue
        key, _score, _method = match_header(header, rtype, min_score=min_score)
        if key is not None:
            continue  # already mapped
        guess, guess_score, _ = match_header(header, rtype, min_score=0.0)
        out.append({"header": header, "norm": norm, "guess": guess, "score": round(guess_score, 3)})
    return out


# --------------------------------------------------------------------------- #
# 3. product spelling harvest  — build_product_synonyms.py:collect_spellings()
# --------------------------------------------------------------------------- #
def harvest_spellings(result: dict) -> list[str]:
    out: list[str] = []
    for row in result.get("rows") or []:
        name = row.get("raw_product_name") or row.get("product_name")
        if not name:
            continue
        name = str(name).strip()
        if name:
            out.append(name)
    return out


def match_spellings_to_master(spellings: dict, catalog: list, min_score: float = 0.90,
                              margin: float = 0.03) -> dict:
    """SCAN ONLY (no mutation): classify each distinct spelling against the catalog
    using build_product_synonyms.py's strict matcher. Returns counts + candidates.

    The actual write is a gated step that calls the real build_product_synonyms CLI,
    so the catalog is never mutated here.
    """
    import build_product_synonyms as _bps  # lazy: PSUI-only catalog CLI (see header note)

    covered = set()
    for product in catalog:
        covered.add(_normalize_name(product.get("canonical_name", "")))
        for syn in product.get("synonyms", []):
            covered.add(_normalize_name(syn))
    covered.discard("")

    index = _bps._build_index(catalog)
    added = defaultdict(list)      # canonical_name -> [spelling]
    unmatched: dict[str, str] = {}
    noise: list[str] = []
    for spelling, div in sorted(spellings.items()):
        norm = _normalize_name(spelling)
        if not norm or norm in covered:
            continue
        if not _bps._is_plausible_product(spelling, norm):
            noise.append(spelling)
            continue
        product = _bps._strict_match(norm, index, min_score, margin)
        if product is not None:
            added[product.get("canonical_name", "?")].append(spelling)
            covered.add(norm)  # so two spellings of one new synonym aren't double counted
        else:
            unmatched[spelling] = div
    return {
        "added": {k: sorted(v) for k, v in added.items()},
        "added_count": sum(len(v) for v in added.values()),
        "unmatched": unmatched,
        "noise_count": len(noise),
    }


# --------------------------------------------------------------------------- #
# 4. misfiled classification  — relocate_misfiled_reports.py:classify()
# --------------------------------------------------------------------------- #
def _has(tokens: set[str], *subs: str) -> bool:
    return any(any(s in t for s in subs) for t in tokens)


def classify_misfiled(result: dict) -> tuple[bool, bool]:
    """(looks_like_stock, looks_like_party) from this file's header tokens."""
    tokens = {str(h).strip().lower() for h in (result.get("headers_detected") or {})}
    open_ = _has(tokens, "opening", "opstk", "op stk", "openstk", "ostk") or {"op", "open"} & tokens
    close_ = (
        _has(tokens, "closing", "closestk", "cls stk", "clstk", "closestock", "curstk", "qoh", "cls.stk")
        or {"cl", "clos"} & tokens
    )
    invoice = _has(tokens, "inv no", "invno", "bill no", "billno", "bill date", "billdate",
                   "invoice", "feedno", "feeddate")
    looks_stock = bool(open_) and bool(close_)
    looks_party = bool(invoice) and not looks_stock
    return looks_stock, looks_party


# --------------------------------------------------------------------------- #
# 5. regression metrics  — regression_test.py:_snapshot() off a cached result
# --------------------------------------------------------------------------- #
def regression_metrics(route: str, file_name: str, result: dict) -> dict:
    rows = result.get("rows") or []
    snap = {
        "file": file_name,
        "route": route,
        "row_count": len(rows),
        "warnings_count": len(result.get("warnings") or []),
        "headers_detected_count": len(result.get("headers_detected") or {}),
    }
    debug = result.get("debug") or {}
    fmt = debug.get("detected_format") or debug.get("layout")
    if fmt:
        snap["detected_format"] = fmt
    if route.startswith("party"):
        snap.update(_party_metrics(rows))
    else:
        snap.update(_stock_metrics(rows))
    snap.update(_completeness_metrics(result))
    return snap
