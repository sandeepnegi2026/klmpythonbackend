"""Generic (non-customer) party-account filter — shared by the party PDF/XLSX pipelines.

Some vendor party reports book counter / cash-memo / walk-in / staff / route-collection
sales against a **generic ledger account** rather than a named customer (e.g. "CASH",
"CASH MEMO", "COUNTER SALE", "WALK IN CUSTOMER", "STAFF <name>", "CASH COLLECTION <city>").
These are real rows but not a real party, so they pollute party-wise sales. The engine
excludes them from the emitted rows.

Two hard invariants:
  1. **Exclusion happens POST-ledger.** The line-accounting ledger (core/line_ledger) runs on
     the FULL parser output first, so these lines stay *claimed* — they are intentionally
     excluded, never counted as dropped/UNEXPLAINED. Callers must filter AFTER line_audit.
  2. **Never remove a real shop.** The matcher is an exact-name / tightly-anchored allowlist,
     proven by `tests`/`party_filter_selftest` to match every confirmed generic account and to
     leave every confirmed real shop that merely *contains* a keyword (e.g. "CASH CHEMIST",
     "GENERAL MEDICAL STORES", "COUNTER MEDICAL STORE-2", "GENERAL PHARMACY- KOVAI MEDICAL
     CENTER...", "SELF CARE CHEMISTS...", "TotalHealth/Total Care ...") untouched.

The allowlist was derived from an adversarial per-file verification sweep of the whole
Final_Data party corpus (raw-source confirmed), NOT guessed. Widen it only with the same
proof, and re-run the full suite (a widened matcher must drop ZERO additional real parties).
"""
from __future__ import annotations

import re

# Exact normalized names (whitespace-collapsed + uppercased). Reserved for vendor-specific
# account labels that would be unsafe to generalize into a pattern (a broad "STAFF <x>"
# pattern could clip a real shop, so the four confirmed staff ledgers are pinned exactly).
_EXACT = frozenset(
    {
        "STAFF PANNELAL",
        "STAFF RAJKUMAR",
        "STAFF RUPINDER",
        "STAFF SURESH VERMA",
    }
)

# Tightly-anchored family patterns. Each was checked to match the confirmed generic accounts
# and to reject every confirmed real shop in the corpus (see _REAL_GUARD in the selftest).
_PATTERNS = tuple(
    re.compile(p)
    for p in (
        r"^CASH$",
        r"^CASH BILL$",
        r"^CASH CUSTOMER$",
        r"^CASH MEMO( SALES? A/?C)?$",            # CASH MEMO, CASH MEMO SALES A/C
        r"^CASH SALES?(\s*-\s*[A-Z].*)?$",        # CASH SALE, CASH SALES, CASH SALES-UDAIPUR
        r"^CASH[\s-]*OFFICE$",                    # CASH-OFFICE
        r"^CASH A/?C\b",                          # CASH A/C , (trailing punctuation ok)
        r"^CASH COLLECTION\b",                    # CASH COLLECTION <CITY> (route accounts)
        r"^COUNTER( SALES?| CUSTOMER| CASH SALE)?$",
        r"^WALK\s*-?\s*IN CUSTOMER$",
        r"^GENERAL SALE\s*\(.*\)\s*$",            # GENERAL SALE ( <own firm> ) — self account
        r"^GENERAL LEDGER/CASH MEMO SALE$",
        r"^SALES RETURN AUDIT$",
        r"^CREDIT NOTE BENEFITS - CENTRAL$",
    )
)


def _norm(name) -> str:
    return re.sub(r"\s+", " ", str(name or "").strip()).upper()


def is_generic_nonparty_account(name) -> bool:
    """True iff `name` is a generic non-customer ledger account (should be excluded from
    party-wise output). False for any real shop, even one containing 'CASH'/'GENERAL'/etc."""
    n = _norm(name)
    if not n:
        return False
    if n in _EXACT:
        return True
    return any(p.search(n) for p in _PATTERNS)


def filter_generic_accounts(rows):
    """Drop rows whose party_name is a generic non-customer account. Returns
    (kept_rows, n_excluded). Rows without a party_name are always kept."""
    kept, excluded = [], 0
    for r in rows:
        if is_generic_nonparty_account(r.get("party_name")):
            excluded += 1
            continue
        kept.append(r)
    return kept, excluded
