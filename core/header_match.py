import re
import threading
from difflib import SequenceMatcher

from .canonical import SYNONYMS


def normalize(value):
    text = "" if value is None else str(value)
    text = re.sub(r"[^a-z0-9]+", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


# --------------------------------------------------------------------------- #
# Manual header overrides (UI-driven, opt-in).
#
# The diagnostic UI lets a user force an unmatched column header onto a canonical
# field, re-run, and confirm the fix before it is made permanent in canonical.py.
# When an override is registered for a report type, match_header returns it
# directly (score 1.0, method "override").
#
# Storage is THREAD-LOCAL: Streamlit serves every browser session from one process
# but runs each session's script in its own thread, so a bare module global would
# let one user's overrides bleed into (or be cleared by) another's concurrent
# extract. Thread-local storage isolates each session. It is also empty by default,
# so normal extraction — and the production Backends service, which never sets it —
# behaves identically (match_header skips the lookup entirely when nothing is set).
# Set/clear it around a single synchronous extract() call.
# --------------------------------------------------------------------------- #
_overrides_store = threading.local()


def set_header_overrides(report_type, overrides):
    """Register/replace manual header→canonical overrides for ``report_type`` on the
    current thread.

    ``overrides`` maps raw header text → canonical field key. Keys are normalized
    so they match however the header appears in the file. Pass a falsy value to
    clear. Always clear (e.g. in a ``finally``) after the extract call.
    """
    data = getattr(_overrides_store, "data", None)
    if data is None:
        data = {}
        _overrides_store.data = data
    if overrides:
        data[report_type] = {
            normalize(k): v for k, v in overrides.items() if normalize(k) and v
        }
    else:
        data.pop(report_type, None)


def get_header_overrides(report_type):
    data = getattr(_overrides_store, "data", None)
    return (data or {}).get(report_type, {})


def _token_score(left, right):
    a = set(normalize(left).split())
    b = set(normalize(right).split())
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# Synonym lists are static, but match_header was re-running normalize() over every
# synonym on every call (millions of redundant re.sub() calls when scoring a whole
# sheet). Precompute the normalized (canonical_key, candidate) pairs once per report
# type — same order, same filtering (drop empties) as the old inline loop, so scoring
# is byte-identical; only the wasted re-normalization is removed.
_NORM_SYNONYMS = {}


def _norm_synonyms(report_type):
    cached = _NORM_SYNONYMS.get(report_type)
    if cached is None:
        cached = [
            (canonical_key, cand)
            for canonical_key, synonyms in SYNONYMS[report_type].items()
            for cand in (normalize(s) for s in synonyms)
            if cand
        ]
        _NORM_SYNONYMS[report_type] = cached
    return cached


def match_header(source_header, report_type, min_score=0.62):
    raw = "" if source_header is None else str(source_header)
    normed = normalize(raw)
    if not normed:
        return None, 0.0, "empty"

    _store = getattr(_overrides_store, "data", None)
    if _store:
        override = _store.get(report_type)
        if override and normed in override:
            return override[normed], 1.0, "override"

    best_key = None
    best_score = 0.0
    best_method = "none"
    for canonical_key, candidate in _norm_synonyms(report_type):
        if normed == candidate:
            return canonical_key, 1.0, "exact"
        # `normed in candidate` (a short header being a SUBSTRING of a longer synonym) is
        # unreliable for 1-2 char headers: the serial column "Sr." (normed "sr") lands
        # inside sales-return synonyms ("srn"/"salesret"/"srtot") and steals the field.
        # Require the header to be >= 3 chars for that direction; the other direction
        # (`candidate in normed`, a known synonym inside a longer header) is unaffected.
        if len(candidate) >= 3 and (
            candidate in normed or (len(normed) >= 4 and normed in candidate)
        ):
            score = 0.88
            method = "contains"
        else:
            token_score = _token_score(normed, candidate)
            ratio_score = SequenceMatcher(None, normed, candidate).ratio()
            score = max(token_score, ratio_score * 0.82)
            method = "fuzzy"
        if score > best_score:
            best_key = canonical_key
            best_score = score
            best_method = method

    if best_score >= min_score:
        return best_key, best_score, best_method
    return None, best_score, "none"


def map_headers_indexed(headers, report_type, min_score=0.62):
    """Resolve headers to canonical fields by COLUMN INDEX, not header text.

    ``map_headers`` keys its result by header *text*, so when a layout repeats the same
    header across several merged columns (e.g. "ITEM DESCRIPTION" spanning 5 columns) the
    duplicates clobber each other and a good mapping (product_name) is lost. This variant
    assigns each canonical key to its single best column and returns ``{col_idx: canonical}``,
    so duplicate-text columns can no longer overwrite a real mapping.

    Tie-break is (score DESC, column index ASC) — identical to ``map_headers``'s stable
    score-sort — so non-duplicate layouts resolve to exactly the same columns as before.
    """
    scored = []
    for i, header in enumerate(headers):
        key, score, _method = match_header(header, report_type, min_score=min_score)
        scored.append((i, key, score))
    by_index = {}
    used = set()
    for i, key, _score in sorted(scored, key=lambda t: (-t[2], t[0])):
        if key and key not in used:
            by_index[i] = key
            used.add(key)
    return by_index


def map_headers(headers, report_type, min_score=0.62):
    candidates = []
    for header in headers:
        key, score, method = match_header(header, report_type, min_score=min_score)
        candidates.append((str(header), key, score, method))
    candidates.sort(key=lambda item: item[2], reverse=True)

    used = set()
    mapped = {}
    col_counter = 0
    for header, key, score, method in candidates:
        if key and key not in used:
            mapped[header] = {"canonical": key, "score": score, "method": method}
            used.add(key)
        else:
            raw_str = normalize(header).replace(" ", "_")
            if not raw_str:
                raw_str = f"col_{col_counter}"
                col_counter += 1
            safe_key = f"raw_{raw_str}"
            suffix = 1
            while safe_key in used:
                safe_key = f"raw_{raw_str}_{suffix}"
                suffix += 1
            mapped[header] = {"canonical": safe_key, "score": score, "method": "unmapped"}
            used.add(safe_key)
    return {header: mapped[header] for header in [str(h) for h in headers]}
