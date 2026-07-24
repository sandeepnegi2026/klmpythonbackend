import json
import os
import re
import threading
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


# ---- count-pack aware disambiguation ------------------------------------------
# A pack COUNT is the number of units in a strip/box: "1*4 Cap" (4 caps), "8'S",
# "10 TAB". This is the count sibling of `_norm_size`: volumetric SKUs are
# `_pack_correct`'s domain; count-only SKUs (e.g. "Klm-D3 60K Capsules (1*4Cap)"
# vs "(1*8 Cap)") have no ml/gm size so they need count evidence to disambiguate.
# Operate on the RAW string (before _normalize_name) because '*' and apostrophes are
# the disambiguating signal and normalization destroys them. `_norm_size` still owns
# volumetric strings — the lookahead below refuses "4X5ML" (4 units of 5ml).
_COUNT_SIZE_LOOKAHEAD = r"(?!\s*(?:mls?|gms?|grams?|gram|kg|ltr|g|l)\b)"
# A: multiplier pack "1*4Cap" / "1X8" / "1 * 10 TAB" -> count = the SECOND number.
_COUNT_MULT_RE = re.compile(
    r"(?<![\d.])(\d{1,3})\s*[*xX]\s*(\d{1,3})(?![\d.])" + _COUNT_SIZE_LOOKAHEAD
    + r"\s*(?:caps?(?:ules?)?|tabs?(?:lets?)?)?", re.I)
# Quote glyphs vendors write between a count and a trailing "S": apostrophe, backtick,
# curly quotes, and the inch double-quote ('4"S' = 4's, seen in real KLM 60K packs).
_CNT_QUOTE = r"['`’‘\"”“]"
# B: count + unit word "4 CAP" / "8CAP" / "8PCS" / "8 NO'S" -> 1-2 digits ONLY, so
#    strengths (250/500/625/1000, all >=3 digits) can never fire here.
_COUNT_UNIT_RE = re.compile(
    r"(?<![\d.])(\d{1,2})(?!\d)\s*(?:caps?(?:ules?)?|tabs?(?:lets?)?|pcs?\b|nos\b|no"
    + _CNT_QUOTE + r"?s)\b", re.I)
# C: N'S count "4'S" / "10S" / "10 S" / "3's" / '4"S' (1-3 digits: allows "100'S" bottles).
_COUNT_SUFFIX_RE = re.compile(r"(?<![\d.])(\d{1,3})(?!\d)\s*" + _CNT_QUOTE + r"?\s*s\b", re.I)


def _norm_count(text):
    """First pack-COUNT token in RAW `text` as 'c<int>' ('c4','c8','c10'), or ''.
    Priority A (multiplier) > B (count+unit) > C (N'S). Returns '' for strengths
    ('625 TAB', '800IU'), volumetric ('30ML', '4X5ML'), and batch/date tokens."""
    if not text:
        return ""
    s = str(text)
    m = _COUNT_MULT_RE.search(s)
    if m:
        return "c" + str(int(m.group(2)))
    m = _COUNT_UNIT_RE.search(s)
    if m:
        return "c" + str(int(m.group(1)))
    m = _COUNT_SUFFIX_RE.search(s)
    if m:
        return "c" + str(int(m.group(1)))
    return ""


def _count_strip(text):
    """RAW text with pattern-A multiplier expressions removed, for key derivation.
    ONLY pattern A is stripped: removing B/C from canonicals would eat
    strength+form-word pairs and collapse distinct products."""
    return _COUNT_MULT_RE.sub(" ", str(text or ""))


def _count_key(name):
    """Count-insensitive brand key: strip pattern-A counts from the RAW canonical,
    then _brand_key(). 'Klm-D3 60K Capsules (1*4Cap)' and '(1*8 Cap)' both ->
    'klm d3 60k'; 'Resoten 10' / 'Resoten 20' stay distinct (strength digits kept)."""
    return _brand_key(_count_strip(name))


# A pack column that LEADS with a standalone multi-digit STRENGTH followed by a
# separate strip-count NUMBER ("1000 3'S", "500 10*10") is a mis-split: the leading
# number is really a STRENGTH that belongs to the product name, stranded here by
# a layout whose name/pack boundary broke before a strength that lacked a form
# word ("HERPIVAL 1000 3'S" -> name "HERPIVAL" + pack "1000 3'S"). The trailing
# \d (another number) is what separates a stranded strength (TWO numbers: strength
# + strip count) from an ordinary single-number pack: "10 STP" (10 strips), "50 ML"
# (50 ml size), "10 TAB" all have ONE number after the space that is a UNIT WORD,
# not a strip count, so they must NOT fire (they would wrongly snap "Klclav Kid Dt"
# with pack "10 STP" to a "Klclav Ds" sibling). Size packs ('30ml','50 ml') are
# _pack_correct's job. 2-4 digits so plain strip counts never lead.
_PACK_STRENGTH_RE = re.compile(r"^\s*(\d{2,4})\s+\d")

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
#   _COUNT_INDEX: dict count_key -> list of (count, product) — same-brand COUNT-pack
#                 siblings (no volumetric size), for count-aware correction
#                 (see _count_pack_correct). Only count-only SKUs are indexed.
_COUNT_INDEX = None
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

# Normalized raw names that are genuinely AMBIGUOUS across a product LINE and must never
# be fuzzy-resolved to an arbitrary catalog-first sibling. "klm d3" spans five real SKUs
# (60K caps 1*4/1*8, nano drops 15/30ml, shots 5ml) plus the not-in-catalog "KLM-D3+"
# (D3 Plus 5ml) — bare "KLM D3" / "KLM-D3+" both normalize here, so the fuzzy containment
# floor would otherwise book them to whichever SKU appears first in the catalog. Consulted
# AFTER the exact-alias index (an explicit alias still wins) and BEFORE the fuzzy loop, so
# these resolve to None (unmatched) unless the catalog explicitly aliases the exact string.
_AMBIGUOUS_STUBS = {"klm d3"}

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
    global _NORM_INDEX, _EXACT_INDEX, _BRAND_INDEX, _COUNT_INDEX, _INDEX_FOR
    catalog = load_master_catalog()
    if _NORM_INDEX is not None and _INDEX_FOR is catalog:
        return
    # (Re)building for a new/changed catalog — drop any memoized resolutions computed
    # against the previous catalog so a swap can never serve a stale hit.
    _NORM_CACHE.clear()
    norm_index = []
    exact_index = {}
    brand_index = {}
    count_index = {}
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
        # Count-pack siblings: only products with NO volumetric size and a real count
        # ("1*4 Cap"), so the count index and _pack_correct's domain never overlap.
        ckey = _count_key(product.get("canonical_name", ""))
        if ckey:
            csize = _norm_size(product.get("pack", "")) or _norm_size(product.get("canonical_name", ""))
            cnt = _norm_count(product.get("pack", "")) or _norm_count(product.get("canonical_name", ""))
            if not csize and cnt:
                count_index.setdefault(ckey, []).append((cnt, product))
    _NORM_INDEX = norm_index
    _EXACT_INDEX = exact_index
    _BRAND_INDEX = brand_index
    _COUNT_INDEX = count_index
    _INDEX_FOR = catalog

# Thread-local pool of one SequenceMatcher per DISTINCT normalized candidate, with its
# seq2 (b) preset to that candidate. difflib rebuilds the b-side char index (__chain_b,
# the dominant per-row cost) on every set_seq2; presetting b ONCE and only calling
# set_seq1(row) per row removes that rebuild. b stays exactly the candidate string, so
# ratio()/quick_ratio() are byte-identical to the old set_seq2-per-row loop — this is a
# pure caching change, not a scoring change. Thread-LOCAL because a SequenceMatcher is
# mutated per use (set_seq1); a shared one would race across the service's request
# threads. Rebuilt per thread when the catalog object changes.
_TL = threading.local()

def _candidate_matchers():
    catalog = load_master_catalog()
    cm = getattr(_TL, "cand_matcher", None)
    if cm is not None and getattr(_TL, "cand_for", None) is catalog:
        return cm
    _build_indexes()
    cm = {}
    for _product, norm_cands in _NORM_INDEX:
        for norm_cand in norm_cands:
            if norm_cand not in cm:
                cm[norm_cand] = SequenceMatcher(None, "", norm_cand)  # b=candidate, __chain_b once
    _TL.cand_matcher = cm
    _TL.cand_for = catalog
    return cm

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

# Confusable-brand veto: a small curated set of catalog brands whose NAMES are
# near-identical strings and therefore fuzzy-match each other — e.g. "Onitraz" vs
# "Zoritraz" (differ by the leading char, share "…traz … cap"). A raw of one brand can
# score higher against the OTHER brand's product than its own, silently relabelling one
# maker's product as a competitor's (1,674 corpus rows did exactly this). They are
# genuinely distinct products, so a raw whose brand is in a confusable group must NEVER
# resolve to a different brand in that group.
_CONFUSABLE_BRAND_GROUPS = [frozenset({"onitraz", "zoritraz"})]

# Dosage-form / pack words that do NOT distinguish one same-brand SKU from another, so they
# are ignored when comparing variant tokens (Onitraz Forte vs Onitraz Sb vs plain Onitraz).
# "forte"/"sb"/strength numbers are NOT here — those are the distinguishing variant tokens.
_CONFUSABLE_FORM_WORDS = frozenset({
    "cap", "caps", "capsule", "capsules", "tab", "tabs", "tablet", "tablets", "ml", "gm",
    "gms", "gram", "grams", "gel", "cream", "lotion", "oint", "ointment", "drop", "drops",
    "syrup", "syp", "susp", "suspension", "soap", "sachet", "inj", "injection", "spray",
    "solution", "soln", "powder", "bar", "kit", "serum", "wash", "emulgel", "mg", "mgs",
})

def _first_token(norm_name):
    return norm_name.split()[0] if norm_name else ""

# Common spelling variants that denote the SAME variant marker, folded so a raw's typo
# doesn't lose the distinction ("onitraz FORT cap" is the FORTE SKU, not the plain one).
_VARIANT_ALIASES = {"fort": "forte"}

def _variant_tokens(norm_name):
    """Distinguishing tokens of a same-brand SKU: drop the brand (first token) and generic
    dosage-form/pack words; keep variant markers (forte, sb) and strength numbers. Folds
    known spelling variants (fort->forte) so a typo'd raw still matches the right variant."""
    toks = norm_name.split()
    return {_VARIANT_ALIASES.get(t, t) for t in toks[1:] if t not in _CONFUSABLE_FORM_WORDS}

def _confusable_brand_correct(norm_raw, result, min_score):
    """If `result` crossed between two confusable brands vs the raw, re-match the catalog
    restricted to the raw's OWN brand and return that instead. Fires ONLY when the original
    match already crossed a confusable pair — and every such cross-match is wrong (the two
    brands are distinct makers), so this can only correct, never regress a good match. Among
    same-brand candidates the winner is chosen by VARIANT fit first (most of the raw's
    distinguishing tokens present, fewest foreign ones), then fuzzy score — so a plain
    'onitraz capsule' picks 'Onitraz Capsules', not 'Onitraz Sb 65'."""
    raw_brand = _first_token(norm_raw)
    if not raw_brand:
        return result
    res_brand = _first_token(_normalize_name(result.get("canonical_name", "")))
    group = next((g for g in _CONFUSABLE_BRAND_GROUPS
                  if raw_brand in g and res_brand in g and raw_brand != res_brand), None)
    if group is None:
        return result
    raw_var = _variant_tokens(norm_raw)
    cm = _candidate_matchers()
    best, best_key = None, None
    for product, norm_cands in _NORM_INDEX:
        if _first_token(norm_cands[0]) != raw_brand:
            continue
        # Variant identity comes from the CANONICAL name (norm_cands[0]) — the authoritative
        # descriptor — NOT the best-matching synonym, whose incidental tokens ("onitraz sb
        # capsule") would otherwise misrank a plain "onitraz capsules" onto "Onitraz Sb 65".
        # A real variant MARKER ("forte"/"sb") outranks a bare pack DIGIT ("1"/"10") — the
        # digit is pack noise embedded in the canonical, not a distinguishing strength, so a
        # plain "onitraz capsule" isn't penalised against "Onitraz Capsules 1*10 Capsules".
        prod_var = _variant_tokens(norm_cands[0])
        matched = raw_var & prod_var
        foreign = prod_var - raw_var
        m_nd = sum(1 for t in matched if not t.isdigit())
        f_nd = sum(1 for t in foreign if not t.isdigit())
        # Fuzzy score = best over this product's synonyms (final tiebreak only).
        s = 0.0
        for nc in norm_cands:
            m = cm[nc]
            m.set_seq1(norm_raw)
            if (nc in norm_raw or norm_raw in nc) and len(nc) >= 4:
                s = max(s, max(0.90, m.ratio()))
            else:
                s = max(s, m.ratio())
        key = (m_nd, len(matched), -f_nd, -len(foreign), s)
        if best_key is None or key > best_key:
            best_key, best = key, product
    return best if best is not None else result

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

    # Ambiguous product-line stub: bare names that span multiple real SKUs must NOT be
    # fuzzy-resolved to a catalog-order-arbitrary sibling. Return unmatched. Placed after
    # the exact index (explicit aliases still win) and before the fuzzy loop.
    if norm_raw in _AMBIGUOUS_STUBS:
        _NORM_CACHE[key] = None
        return None

    best_match = None
    best_score = 0.0
    # One prebuilt matcher per candidate (seq2/b = the candidate, char index built once);
    # per candidate we only set_seq1(norm_raw), so b's index is reused instead of rebuilt.
    # b is unchanged from the old loop, so every score is byte-identical.
    cand_matcher = _candidate_matchers()
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
            matcher = cand_matcher[norm_cand]  # b = norm_cand, index prebuilt
            # Containment bonus if lengths are somewhat close to avoid matching tiny substrings
            if (norm_cand in norm_raw or norm_raw in norm_cand) and len(norm_cand) >= 4:
                # Floor of 0.90, but never DEMOTE a contained candidate whose real
                # similarity exceeds 0.90 below a loosely-contained rival that also
                # hits the flat 0.90 (a generic alias like "nevlon moisturizing"
                # otherwise ties and wins on catalog order). set_seq1 first so ratio()
                # is available for this candidate.
                matcher.set_seq1(norm_raw)
                score = max(0.90, matcher.ratio())
            else:
                cand_len = len(norm_cand)
                if min(raw_len, cand_len) < len_gate * max(raw_len, cand_len):
                    continue  # length ratio too skewed for ratio() to reach min_score
                # quick_ratio() >= ratio() always, so if the cheap upper bound can't beat the
                # current best, the real ratio can't either — skip it. Result is unchanged.
                matcher.set_seq1(norm_raw)
                if matcher.real_quick_ratio() <= best_score or matcher.quick_ratio() <= best_score:
                    continue
                score = matcher.ratio()

            if score > best_score:
                best_score = score
                best_match = product

    result = best_match if best_score >= min_score else None
    if result is not None:
        result = _confusable_brand_correct(norm_raw, result, min_score)
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


def _count_pack_correct(master, cnt):
    """Count-aware variant correction, the count sibling of `_pack_correct`. When
    `master` (a confident BRAND match) carries a different pack COUNT than the row's
    extracted `cnt`, return the SAME-BRAND count-only sibling whose pack count == `cnt`.
    Returns None (keep the base match) unless exactly one form-compatible sibling exists
    — never changes the brand, never invents a match, never crosses form groups (cap ->
    tab). This turns a base "Klm-D3 60K Capsules (1*8 Cap)" hit into the "(1*4Cap)"
    sibling when the row pack says "1*4CAP"."""
    if not cnt or master is None:
        return None
    mp = _norm_count(master.get("pack", "")) or _norm_count(master.get("canonical_name", ""))
    if mp == cnt:
        return None  # base match already has the right count (e.g. "RESOTEN-10 CAP" no-op)
    _build_indexes()
    ckey = _count_key(master.get("canonical_name", ""))
    if not ckey:
        return None
    sibs = _COUNT_INDEX.get(ckey)
    if not sibs:
        return None
    mg = _form_groups(master.get("canonical_name", ""))
    matches = {}
    for c, product in sibs:
        if c != cnt:
            continue
        pg = _form_groups(product.get("canonical_name", ""))
        if mg and pg and not (mg & pg):
            continue  # never cross form groups (capsule -> tablet)
        matches[product.get("code") or product.get("canonical_name")] = product
    if len(matches) != 1:
        return None  # no count-matched sibling, or ambiguous -> keep base, never invent
    cand = next(iter(matches.values()))
    if cand.get("canonical_name") == master.get("canonical_name"):
        return None
    return cand


# Form-GROUP model for cross-form mismatch detection. Distinct groups almost never
# share a product, so a raw whose form-group is DISJOINT from the matched product's is
# the wrong FORM (e.g. "XEPIBACT CREAM" -> "Xepibact 500 Tablets", "SOFIDEW BABY LOTION"
# -> "Sofidew Baby Massage Oil"). Equivalences live INSIDE a group so spelling variants
# never false-flag (oint==ointment, gel==emulgel, softgel==capsule, syrup==suspension).
# DELIBERATELY CONSERVATIVE: only UNAMBIGUOUS form words are listed. Ambiguous ones
# ("solution", "drops", "spray", "serum", bare "wash"/"foam") are OMITTED so they can
# never trigger a false veto (a topical "solution" vs a "lotion" must not unmatch). Within
# a group the finer sub-form (cream vs lotion vs gel) is NOT gated here — a coarser, safer
# first cut. Mirror of scripts/validate_master_coverage.py's oracle.
_FORM_GROUP = {}
for _grp, _words in {
    "oral_solid": ["tablet", "tablets", "tab", "tabs", "capsule", "capsules", "cap", "caps", "softgel"],
    "oral_liquid": ["syrup", "syp", "suspension", "susp"],
    "topical": ["cream", "ointment", "oint", "gel", "emulgel", "lotion", "paste"],
    "wash": ["soap", "bar", "shampoo", "facewash", "wash", "cleanser", "foam"],
    "powder": ["powder"], "oil": ["oil"],
}.items():
    for _w in _words:
        _FORM_GROUP[_w] = _grp


def _form_groups(text):
    """Set of form GROUPS present in `text`. 'soft gel'/'gelatin' collapse to the
    oral_solid (softgel capsule) group; otherwise each recognised form word maps to
    its group. Unrecognised / ambiguous words contribute nothing."""
    t = (text or "").lower()
    out = set()
    # "gelatin" (soft-gelatin capsule) is unambiguously oral_solid.
    if "gelatin" in t:
        out.add("oral_solid")
    # A bare "soft gel" phrase is AMBIGUOUS — "Ekran Soft Gel" is a topical silicon gel
    # while "Extend Gold Soft Gel" is a soft-gelatin capsule — so neutralise the phrase
    # (contribute no form group) rather than mis-read it. The single token "softgel" and
    # "gelatin" still count as the capsule form.
    t = re.sub(r"\bsoft\s+gel\b", " ", t)
    for w in re.findall(r"[a-z]+", t):
        g = _FORM_GROUP.get(w)
        if g:
            out.add(g)
    return out


def _form_correct(master, form_text, size):
    """Cross-form-group correction. When the row's raw form-group is DISJOINT from the
    matched master's form-group, the base match is the wrong FORM. Snap to the same-brand
    sibling whose form-group matches the raw (and pack size, when known); if exactly one
    such sibling does not exist, return None to VETO the match — the row then stays raw +
    unmatched and is flagged for review, rather than keep a confidently-wrong form
    (cream booked as tablets). Sibling-existence-gated exactly like _pack_correct, so a
    row whose form is compatible or absent is returned unchanged and the only real
    candidate is never blindly demoted."""
    if master is None:
        return master
    rg = _form_groups(form_text)
    mg = _form_groups(master.get("canonical_name", ""))
    if not rg or not mg or (rg & mg):
        return master  # no form info on one side, or compatible -> keep base match
    _build_indexes()
    bkey = _brand_key(master.get("canonical_name", ""))
    if not bkey:
        return master
    cands = {}
    for s_size, product in _BRAND_INDEX.get(bkey, []):
        if (_form_groups(product.get("canonical_name", "")) & rg) and (not size or s_size == size):
            cands[product.get("code") or product.get("canonical_name")] = product
    if len(cands) == 1:
        return next(iter(cands.values()))   # unique correct-form sibling -> snap
    return None  # no / ambiguous correct-form sibling -> veto (flag for review)


def _recover_pack_strength(raw_name, pack_txt, master):
    """Strength stranded in the pack column. A layout can split "HERPIVAL 1000 3'S"
    into name "HERPIVAL" + pack "1000 3'S", so the bare name snaps to the DEFAULT
    strength sibling ("Herpival-500") while the real strength (1000) sits unused in
    the pack. When the pack LEADS with a standalone multi-digit strength the name
    lacks, re-match on "name + pack" and adopt the result ONLY when it is a
    different SAME-BRAND product (never cross-brand, never enriches an unmatched
    row). Returns the corrected sibling, or None to keep the base match.

    Note mg<->G equivalence (1000mg == "1 G"): the strength need not appear literally
    in the sibling's canonical — the re-match resolves it via the sibling's synonyms
    ("HERPIVAL 1000 3"), so the gate is the SAME-BRAND + different-result outcome,
    not a literal strength check on the canonical."""
    if master is None or not pack_txt:
        return None
    m = _PACK_STRENGTH_RE.match(str(pack_txt))
    if not m:
        return None
    strength = m.group(1)
    if strength in re.findall(r"\d+", _normalize_name(raw_name)):
        return None  # strength already in the name -> nothing was stranded
    cand = normalize_product(f"{raw_name} {pack_txt}")
    if cand is None:
        return None
    mc = master.get("canonical_name", "")
    cc = cand.get("canonical_name", "")
    if cc == mc:
        return None  # augmented name resolves to the same product -> no change
    mb, cb = _normalize_name(mc).split(), _normalize_name(cc).split()
    if not mb or not cb or mb[0] != cb[0]:
        return None  # different brand word -> refuse (only strength should differ)
    return cand


def _prefer_full_name(raw_full, full, stub):
    """Decide whether the FULL pre-strip name's fuzzy match should replace the stub
    match. The pack-strip can drop a STRENGTH/variant token ("KL CLAV 625 TAB" ->
    stub "KL CLAV" -> wrong "Klclav Ds"); the full name still matches "Klclav-625
    Tablets". Adopt the full match ONLY when the raw supports it:
      (a) every NUMBER in the matched name appears in the raw — blocks wrong
          strength/size drift (adopting a 250ml/375 when the raw says 100ml/625);
      (b) the matched product's leading brand word appears in the raw (de-spaced) —
          blocks wrong-brand drift (Onitraz -> Zoritraz).
    Both must hold, so on any doubt the stub match is kept (no change)."""
    if not full or full is stub:
        return False
    fc = full.get("canonical_name", "")
    sc = stub.get("canonical_name", "") if stub else ""   # stub may be None (no stub match)
    raw_norm = _normalize_name(raw_full)

    def _strength_nums(text):
        # Numbers that are STRENGTH/count tokens, i.e. NOT part of a pack SIZE
        # ("Ga-12 Cream 30Gm" -> {12}: 12 is strength, 30 is the 30gm size). Pack
        # size is the raw column's job (often omitted from the name) and is handled
        # by _pack_correct, so it must not gate this decision.
        t = _normalize_name(text)
        size = {m.group(1) for m in _SIZE_RE.finditer(t)}
        return set(re.findall(r"\d+", t)) - size

    full_s, stub_s, raw_s = _strength_nums(fc), _strength_nums(sc), _strength_nums(raw_norm)
    # (a) every STRENGTH number in the matched name must appear in the raw — blocks
    #     wrong-strength drift (adopting Klclav-375 when the raw says 625).
    if not full_s.issubset(raw_s):
        return False
    # (b) the match must RECOVER a strength the stub lacks (the token the pack-strip
    #     peeled off). Blocks arbitrary same-brand swaps on no-strength variants
    #     (Kid Dt <-> Ds) and pure size variants (left to _pack_correct).
    if not (full_s - stub_s):
        return False
    # (c) the matched product's brand word must appear in the raw (de-spaced) —
    #     blocks wrong-brand drift (Onitraz -> Zoritraz).
    toks = _normalize_name(fc).split()
    brand = toks[0] if toks else ""
    if brand and brand not in raw_norm.replace(" ", ""):
        return False
    return True


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
            # Full-name preference: the stub can lose a strength/variant token that
            # the pack-strip peeled off. If the FULL pre-strip name fuzzy-matches a
            # product the raw genuinely supports (brand + all numbers present), trust
            # it over the stub. Gated by _prefer_full_name so wrong-brand/wrong-size
            # drift is rejected. Memoized on the prestrip key.
            if prestrip:
                if prestrip in _seen:
                    full = _seen[prestrip]
                else:
                    full = normalize_product(prestrip)
                    _seen[prestrip] = full
                if _prefer_full_name(prestrip, full, master):
                    master = full
        # Strength stranded in the pack column: when no full pre-strip name was
        # stashed, a layout may have split off a STRENGTH into the pack ("HERPIVAL
        # 1000 3'S" -> name "HERPIVAL" + pack "1000 3'S"), so the bare name snapped
        # to the default sibling. Re-match on name+pack and snap to the correct
        # same-brand strength variant. Only fires without a prestrip (the prestrip
        # path already carries the full name).
        if master is not None and not prestrip:
            recovered = _recover_pack_strength(raw_name, row.get("pack"), master)
            if recovered is not None:
                master = recovered
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
            else:
                # No volumetric size -> try COUNT-pack correction (1*4 Cap vs 1*8 Cap).
                # Mutually exclusive with _pack_correct by the size guard, so the ml/gm
                # path is never disturbed. Count read like size: pre-strip, pack, raw.
                cnt = (_norm_count(prestrip) or _norm_count(row.get("pack"))
                       or _norm_count(raw_name))
                if cnt:
                    better = _count_pack_correct(master, cnt)
                    if better is not None:
                        master = better
        # Cross-form-group correction: when the raw names a different FORM than the
        # matched product (cream vs tablet, lotion vs oil, soap vs lotion), snap to the
        # correct-form same-brand sibling, or VETO the match (leave the row unmatched +
        # flagged) when no such sibling exists. Form is read from the full pre-strip
        # name and the (form-preserving) raw product name.
        if master is not None:
            master = _form_correct(master, f"{prestrip or ''} {raw_name}", size)
        if master:
            row["raw_product_name"] = raw_name
            row["product_name"] = master.get("canonical_name", raw_name)
            row["canonical_name"] = master.get("canonical_name", raw_name)
            # Stable master product code — carried through so the downstream DB/edge can
            # honour the exact product identity instead of re-guessing by name (Phase 4).
            # Additive: not part of any regression metric.
            if master.get("code"):
                row["product_code"] = master["code"]

            if "pack" in master:
                row["raw_pack"] = row.get("pack", "")
                row["pack"] = master["pack"]
                
            if "division" in master:
                row["raw_division"] = row.get("division", "")
                row["division"] = master["division"]
                
    return rows
