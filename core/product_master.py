import json
import os
import re
from difflib import SequenceMatcher

def _normalize_name(name):
    if not name:
        return ""
    text = re.sub(r"[^a-zA-Z0-9]+", " ", str(name).lower())
    return re.sub(r"\s+", " ", text).strip()


# ---- pack-size aware disambiguation -------------------------------------------
# A pack SIZE is a volumetric/weight token: 50ml, 30gm, 100g, 1.5l. `mg` is
# deliberately EXCLUDED — it is a STRENGTH, not a pack size, so "Onitraz 100Mg"
# is never treated as a size variant. Units are ordered longest-first so 'gm'
# wins over 'g' and 'mls' over 'ml'.
_SIZE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(mls|ml|gms|gm|grams|gram|kg|ltr|g|l)\b", re.I)
_SIZE_UNIT = {"ml": "ml", "mls": "ml", "gm": "gm", "gms": "gm", "g": "gm",
              "gram": "gm", "grams": "gm", "kg": "kg", "ltr": "l", "l": "l"}
# Dosage-FORM words dropped when computing a brand key, so cross-form pack siblings
# group together: "Zydip-C Cream 20 Gm" and "Zydip-C Lotion 50 Ml" share brand
# key "zydip c". Strength digits ("Resoten 10" vs "20") are KEPT, so distinct
# strengths never collapse into one brand.
_FORM_WORDS = {"cream", "lotion", "gel", "ointment", "oint", "tablet", "tablets",
               "tab", "tabs", "capsule", "capsules", "cap", "caps", "soap", "drop",
               "drops", "solution", "suspension", "syrup", "syp", "powder", "oil",
               "shampoo", "spray", "serum", "wash", "facewash", "cleanser", "scrub",
               "mask", "foam", "liquid", "kit", "sachet", "sachets", "shots", "shot"}


def _norm_size(text):
    """First volumetric/weight size token in `text` as a normalized string
    ('50ml', '30gm', '1.5l'), or '' when there is none (e.g. count packs like
    '1*10 tab', or mg strengths)."""
    if not text:
        return ""
    m = _SIZE_RE.search(str(text))
    if not m:
        return ""
    unit = _SIZE_UNIT.get(m.group(2).lower())
    if not unit:
        return ""
    num = m.group(1)
    if num.endswith(".0"):
        num = num[:-2]
    return f"{num}{unit}"


def _brand_key(name):
    """Normalized brand key = product name with pack SIZE tokens and dosage-FORM
    words removed. Used to group same-brand pack siblings for size correction."""
    norm = _normalize_name(name)
    if not norm:
        return ""
    norm = _SIZE_RE.sub(" ", norm)  # drop glued/spaced size tokens ('50gm','50 gm')
    toks = [t for t in norm.split() if t not in _FORM_WORDS]
    return " ".join(toks).strip()

_PRODUCT_MASTER = None
# Derived indexes, built once from the catalog (see _build_indexes):
#   _NORM_INDEX : list of (product, [normalized_candidate, ...])  — precomputed so the
#                 per-candidate _normalize_name() regex runs ONCE at load, not once per row.
#   _EXACT_INDEX: dict normalized_candidate -> product (first occurrence in catalog order
#                 wins) so an exact hit is an O(1) lookup instead of scanning 6k candidates.
_NORM_INDEX = None
_EXACT_INDEX = None
#   _BRAND_INDEX: dict brand_key -> list of (normalized_size, product) — same-brand
#                 pack siblings, for size-aware variant correction (see _pack_correct).
_BRAND_INDEX = None
# The catalog object the indexes were built from. Dev tools (_hijack_audit, _pinpoint,
# _forensic, _hijack_fast) swap `_PRODUCT_MASTER` to a different catalog between calls to
# compare resolutions; guard on object identity so the indexes rebuild when the catalog
# changes instead of silently serving a stale index. Runtime sets the catalog once, so
# this rebuilds at most once there.
_INDEX_FOR = None
# Process-level memo for normalize_product results: (norm_raw, min_score) -> product|None.
# A name resolves identically for a fixed catalog, so caching lets enrichment and triage's
# product_master_match_rate share ONE computation instead of each running the ~6k-candidate
# fuzzy scan. Cleared in _build_indexes() whenever the catalog object changes (dev tools swap
# it), and consulted only AFTER _build_indexes() so a stale cross-catalog result is impossible.
_NORM_CACHE = {}
# Wholesale-clear ceiling: product-name cardinality is small and names repeat heavily, so this
# is only insurance against an unbounded run of distinct unknown names.
_NORM_CACHE_MAX = 50000

def load_master_catalog():
    global _PRODUCT_MASTER
    if _PRODUCT_MASTER is not None:
        return _PRODUCT_MASTER

    # Path relative to core/product_master.py -> ../data/product_master.json
    catalog_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "product_master.json")
    if not os.path.exists(catalog_path):
        _PRODUCT_MASTER = []
        return _PRODUCT_MASTER

    try:
        with open(catalog_path, "r", encoding="utf-8") as f:
            _PRODUCT_MASTER = json.load(f)
    except Exception:
        _PRODUCT_MASTER = []

    return _PRODUCT_MASTER

def _build_indexes():
    """Precompute normalized candidates + an exact-match dict from the catalog.

    The catalog carries ~6k candidate strings (canonical names + harvested synonyms).
    The original matcher re-normalized every candidate on every row and scanned the whole
    list even for exact hits, so enrichment cost ~190 ms/row. These indexes make the
    common case (exact synonym hit) O(1) and remove the per-row normalization, WITHOUT
    changing which product a name resolves to. Built once, cached at module level.
    """
    global _NORM_INDEX, _EXACT_INDEX, _BRAND_INDEX, _INDEX_FOR
    catalog = load_master_catalog()
    if _NORM_INDEX is not None and _INDEX_FOR is catalog:
        return
    # (Re)building for a new/changed catalog — drop any memoized resolutions computed
    # against the previous catalog so a swap can never serve a stale hit.
    _NORM_CACHE.clear()
    norm_index = []
    exact_index = {}
    brand_index = {}
    for product in catalog:
        candidates = [product.get("canonical_name", "")] + product.get("synonyms", [])
        norm_cands = []
        for candidate in candidates:
            norm_cand = _normalize_name(candidate)
            if not norm_cand:
                continue
            norm_cands.append(norm_cand)
            # First product in catalog order to own a candidate wins — mirrors the
            # original loop, which returned on the first exact candidate it reached.
            exact_index.setdefault(norm_cand, product)
        norm_index.append((product, norm_cands))
        # Group same-brand pack siblings for size-aware variant correction. Size
        # comes from the clean `pack` field, falling back to a size embedded in the
        # canonical name.
        bkey = _brand_key(product.get("canonical_name", ""))
        if bkey:
            size = _norm_size(product.get("pack", "")) or _norm_size(product.get("canonical_name", ""))
            brand_index.setdefault(bkey, []).append((size, product))
    _NORM_INDEX = norm_index
    _EXACT_INDEX = exact_index
    _BRAND_INDEX = brand_index
    _INDEX_FOR = catalog

def _exact_lookup(name):
    """O(1) exact/alias index hit for `name` (canonical name or harvested synonym),
    normalized identically to normalize_product. NO fuzzy matching: returns the
    owning product dict only when the catalog explicitly knows this exact string,
    else None."""
    if not name:
        return None
    if not load_master_catalog():
        return None
    norm = _normalize_name(name)
    if not norm:
        return None
    _build_indexes()
    return _EXACT_INDEX.get(norm)

def normalize_product(raw_name, min_score=0.85):
    """
    Fuzzy matches a raw product name against the master catalog.
    Returns the master product dict if a match is found (score >= min_score),
    otherwise returns None.
    """
    if not raw_name:
        return None

    if not load_master_catalog():
        return None

    norm_raw = _normalize_name(raw_name)
    if not norm_raw:
        return None

    _build_indexes()

    # Memo consulted AFTER _build_indexes so a catalog swap has already cleared it. A given
    # (norm_raw, min_score) resolves deterministically for a fixed catalog, so a cached value
    # is byte-identical to recomputing — this only avoids the duplicate fuzzy scan (enrichment
    # fills it; triage's product_master_match_rate then hits it).
    key = (norm_raw, min_score)
    if key in _NORM_CACHE:
        return _NORM_CACHE[key]

    # Exact match — identical result to the original loop's immediate return, O(1).
    hit = _EXACT_INDEX.get(norm_raw)
    if hit is not None:
        _NORM_CACHE[key] = hit
        return hit

    best_match = None
    best_score = 0.0
    # Reuse one matcher: seq1 (norm_raw) is processed once; only seq2 changes per candidate.
    matcher = SequenceMatcher(None, norm_raw)
    # Length gate: ratio() = 2*matches/(len_a+len_b) <= 2*min_len/(len_a+len_b), so a
    # candidate whose length ratio min/max < min_score/(2-min_score) can NEVER reach
    # min_score. Skipping it avoids building SequenceMatcher's per-candidate match table
    # (the dominant cost when a product isn't in the catalog). Any skipped candidate has
    # ratio < min_score, so it can neither become the returned match nor cross the
    # threshold — the result is identical. Containment matches (score 0.90) are exempt.
    len_gate = min_score / (2 - min_score)
    raw_len = len(norm_raw)

    for product, norm_cands in _NORM_INDEX:
        for norm_cand in norm_cands:
            # Containment bonus if lengths are somewhat close to avoid matching tiny substrings
            if (norm_cand in norm_raw or norm_raw in norm_cand) and len(norm_cand) >= 4:
                # Floor of 0.90, but never DEMOTE a contained candidate whose real
                # similarity exceeds 0.90 below a loosely-contained rival that also
                # hits the flat 0.90 (a generic alias like "nevlon moisturizing"
                # otherwise ties and wins on catalog order). set_seq2 first so ratio()
                # is available for this candidate.
                matcher.set_seq2(norm_cand)
                score = max(0.90, matcher.ratio())
            else:
                cand_len = len(norm_cand)
                if min(raw_len, cand_len) < len_gate * max(raw_len, cand_len):
                    continue  # length ratio too skewed for ratio() to reach min_score
                # quick_ratio() >= ratio() always, so if the cheap upper bound can't beat the
                # current best, the real ratio can't either — skip it. Result is unchanged.
                matcher.set_seq2(norm_cand)
                if matcher.real_quick_ratio() <= best_score or matcher.quick_ratio() <= best_score:
                    continue
                score = matcher.ratio()

            if score > best_score:
                best_score = score
                best_match = product

    result = best_match if best_score >= min_score else None
    if len(_NORM_CACHE) >= _NORM_CACHE_MAX:
        _NORM_CACHE.clear()  # bound memory; only re-warms
    _NORM_CACHE[key] = result
    return result

def _pack_correct(master, size):
    """Size-aware variant correction. When `master` (a confident BRAND match from the
    exact/fuzzy step) carries a different pack size than the row's extracted `size`,
    return the SAME-BRAND catalog sibling whose pack == `size`. Returns None (keep the
    base match) unless exactly one such sibling exists — never changes the brand, never
    invents a match for a row that had none. This is what turns a base "Zydip-C" hit
    into "Zydip-C Lotion 50 Ml" for an extracted "50ml" instead of the wrong "Cream 20 Gm"."""
    if not size or master is None:
        return None
    if _norm_size(master.get("pack", "")) == size:
        return None  # base match already has the right size
    _build_indexes()
    bkey = _brand_key(master.get("canonical_name", ""))
    if not bkey:
        return None
    sibs = _BRAND_INDEX.get(bkey)
    if not sibs:
        return None
    matches = {}
    for s, product in sibs:
        if s == size:
            matches[product.get("code") or product.get("canonical_name")] = product
    if len(matches) != 1:
        return None  # no size-matched sibling, or ambiguous across forms -> keep base
    cand = next(iter(matches.values()))
    if cand.get("canonical_name") == master.get("canonical_name"):
        return None
    return cand


def enrich_rows_with_master(rows):
    """
    Takes a list of canonical rows and enriches them using the product master catalog.
    If a product is matched, the original product_name, pack, and division are preserved
    as raw_*, and the canonical master values take their place.
    """
    # Memoize per call: report rows repeat the same product many times, so match each
    # distinct raw name once instead of re-scanning the catalog for every duplicate row.
    _seen = {}
    for row in rows:
        # Full pre-strip product string stashed by a pipeline/layout whose pack-strip
        # CHANGED the name (a strength/size token can be mistaken for a pack, and the
        # bare stub may fuzzy-snap to the WRONG canonical: "RESOTEN 10 TAB" and
        # "RESOTEN 20 TAB" both strip to "RESOTEN" -> "Resoten 10"). Popped
        # unconditionally so the row shape downstream is unchanged.
        prestrip = row.pop("_prestrip_name", None)
        raw_name = row.get("product_name")
        if not raw_name:
            continue

        master = None
        if prestrip:
            # HIGH-CONFIDENCE first: O(1) exact/alias index hit on the FULL name,
            # never fuzzy. On a miss we fall through to exactly today's path on the
            # stripped name, so behavior only changes when the catalog explicitly
            # knows the full string.
            master = _exact_lookup(prestrip)
        if master is None:
            if raw_name in _seen:
                master = _seen[raw_name]
            else:
                master = normalize_product(raw_name)
                _seen[raw_name] = master
        # Size-aware variant correction: keep the confident brand match, but if the
        # row's extracted pack size names a different same-brand sibling, snap to it.
        # Size is read from the full pre-strip name first (it still carries the token),
        # then the extracted `pack`. NOT cached in _seen — it varies per row.
        if master is not None:
            # Size can live in the full pre-strip name, the extracted pack, OR still
            # inside the raw product name (layouts like customer_product_sales keep
            # "ZYDIP LOTION 50ML CQ5105" whole — size embedded, pack empty).
            size = (_norm_size(prestrip) or _norm_size(row.get("pack"))
                    or _norm_size(raw_name))
            if size:
                better = _pack_correct(master, size)
                if better is not None:
                    master = better
        if master:
            row["raw_product_name"] = raw_name
            row["product_name"] = master.get("canonical_name", raw_name)
            row["canonical_name"] = master.get("canonical_name", raw_name)

            
            if "pack" in master:
                row["raw_pack"] = row.get("pack", "")
                row["pack"] = master["pack"]
                
            if "division" in master:
                row["raw_division"] = row.get("division", "")
                row["division"] = master["division"]
                
    return rows
