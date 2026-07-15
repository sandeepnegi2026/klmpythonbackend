#!/usr/bin/env python3
"""
Build product-name synonyms into product_master.json from real vendor reports.

Walks the entire Data tree, runs the existing route extractors over every PDF/Excel
report, collects every distinct product-name spelling, and appends each spelling that
matches an existing master product (fuzzy score >= --min-score) as a new `synonym`.

It NEVER invents canonical products: spellings that match nothing are written to an
"unmatched" report for manual review. It only appends — existing products and synonyms
are never renamed or removed, so re-running is idempotent.

This is a DATA change, not a parser change (AGENTS.md): no extractor/detect/parse logic
is touched. Because it changes how rows are canonicalized, run scripts/regression_test.py
before and after; only `sample_products` should shift.

Usage:
  python scripts/build_product_synonyms.py                 # dry-run: report only, writes nothing
  python scripts/build_product_synonyms.py --apply         # write both product_master.json copies
  python scripts/build_product_synonyms.py --min-score 0.9 # stricter matching
  python scripts/build_product_synonyms.py --data-root "D:/Devs/Reports/Data"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # .../Projects/Backends
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import core.product_master as pm
from core.product_master import _normalize_name

from extractors.party_pdf.pipeline import extract as extract_party_pdf
from extractors.party_xlsx.pipeline import extract as extract_party_xlsx
from extractors.stock_pdf.pipeline import extract as extract_stock_pdf
from extractors.stock_xlsx.pipeline import extract as extract_stock_xlsx

PROJECTS = ROOT.parent                              # .../Projects
DEFAULT_DATA_ROOT = PROJECTS.parent / "Data"        # .../Reports/Data

# product_master.json lives in both the Backends and Python-Service-UI mirrors; keep
# identical. Paths are absolute from Projects/ so this works run from either copy.
MASTER_PATHS = [
    PROJECTS / "Backends" / "data" / "product_master.json",
    PROJECTS / "Python-Service-UI" / "data" / "product_master.json",
]

REPORT_EXTS = {".pdf", ".xls", ".xlsx"}             # everything else is skipped


def _route_for(path: Path):
    """Pick (route_name, extractor) from folder hint + filename route tag.

    The "party_wise"/"_party_product" forms cover the vendor-export drops
    (e.g. "party_wise-26 June", "..._party_product_xlsx") alongside the legacy
    "Party Wise/" tree. A stock hint (the "sales and stock" folder or a
    "_stock_sales" suffix) overrides, so a misfiled "STOCK-SALES ..._party_product"
    file still routes to stock. Mirrors build_header_synonyms._route_for; the
    filename route tag is authoritative over the folder (NEW_BATCH_RUNBOOK Rule 1)."""
    ext = path.suffix.lower()
    is_xlsx = ext in (".xls", ".xlsx")
    s = str(path).lower()
    party_hint = ("party wise" in s) or ("party_wise" in s) or ("party_product" in s)
    stock_hint = ("sales and stock" in s) or ("stock and sales" in s) or ("stock_sales" in s)
    is_party = party_hint and not stock_hint
    if is_party:
        return ("party_xlsx", extract_party_xlsx) if is_xlsx else ("party_pdf", extract_party_pdf)
    return ("stock_xlsx", extract_stock_xlsx) if is_xlsx else ("stock_pdf", extract_stock_pdf)


def _division_hint(path: Path) -> str:
    """Best-effort division label (report only, not used for matching).

    Prefer the vendor sample filename prefix '<DIVISION>_[Sample]_...'; fall back
    to a legacy folder named '<DIVISION> DIVISION'."""
    m = re.match(r"^([A-Za-z][A-Za-z -]*?)_\[Sample\]_", path.name)
    if m:
        return m.group(1).strip().upper()
    for part in path.parts:
        up = part.upper()
        if up.endswith("DIVISION"):
            return up.replace("DIVISION", "").strip()
    return ""


# --- Strict synonym matching ------------------------------------------------
# The runtime matcher (core.product_master.normalize_product) leans on a
# containment bonus that is fine for clean rows but disastrous for the noisy
# spellings real reports throw off (footer blobs, bill refs, bare brand tokens).
# Adding those as synonyms would poison the catalog, so capture uses its own
# conservative matcher: clean the spelling, restrict to same-brand products,
# require a high guarded score, an unambiguous winner, and compatible numbers.

import re
from difflib import SequenceMatcher

# Footer / statement noise that the extractors sometimes emit as a "product".
_NOISE_MARKERS = (
    "pending", "debit note", "short expiry", "non moving", "purchase bill",
    "list of products", "without stock", "opening stock", "closing stock",
    "grand total", "sub total", "stands for",
)


def _tokens(norm: str) -> list[str]:
    return norm.split()


def _brand_token(norm: str) -> str:
    """First alphabetic token >= 3 chars (skips leading serial numbers like '1'
    and the 'klm' manufacturer prefix some vendors prepend)."""
    for tok in norm.split():
        if tok == "klm":
            continue
        if tok.isalpha() and len(tok) >= 3:
            return tok
    return ""


def _brand_ok(b1: str, b2: str) -> bool:
    """Same brand, allowing spacing variants like 'cosmo q' vs 'cosmoq'
    (one is a prefix of the other, shorter side >= 4 chars)."""
    if not b1 or not b2:
        return False
    if b1 == b2:
        return True
    short, long = (b1, b2) if len(b1) <= len(b2) else (b2, b1)
    return len(short) >= 4 and long.startswith(short)


def _numset(norm: str) -> set[str]:
    return set(re.findall(r"\d+", norm))


def _is_plausible_product(spelling: str, norm: str) -> bool:
    """Reject footer blobs, sentences, bare fragments, and number-only noise."""
    if not norm:
        return False
    low = spelling.lower()
    if any(m in low for m in _NOISE_MARKERS):
        return False
    if len(norm) < 6 or len(norm) > 60:
        return False
    if len(_tokens(norm)) > 8:
        return False
    if sum(c.isalpha() for c in norm) < 3:
        return False
    if not _brand_token(norm):
        return False
    return True


def _guarded_score(a: str, b: str) -> float:
    """SequenceMatcher ratio, with a containment bonus gated on similar length
    so '10' (in a long name) or a footer (containing a name) can't score high."""
    if a == b:
        return 1.0
    if len(a) >= 4 and len(b) >= 4 and (a in b or b in a):
        short, long = (a, b) if len(a) <= len(b) else (b, a)
        if len(short) / len(long) >= 0.65:
            return 0.93
    return SequenceMatcher(None, a, b).ratio()


def _build_index(catalog: list) -> list:
    """Precompute (product, brand, canon_nums, [candidate_norms]) per product."""
    index = []
    for product in catalog:
        canon = _normalize_name(product.get("canonical_name", ""))
        cands = [canon] + [_normalize_name(s) for s in product.get("synonyms", [])]
        cands = [c for c in cands if c]
        index.append({
            "product": product,
            "brand": _brand_token(canon),
            "nums": _numset(canon),
            "cands": cands,
        })
    return index


def _strict_match(norm: str, index: list, min_score: float, margin: float):
    """Return the product `norm` confidently belongs to, or None.

    Guards: same brand token, guarded score >= min_score, an unambiguous winner
    (margin over the runner-up), and no conflicting pack/strength numbers.
    """
    brand = _brand_token(norm)
    spel_nums = _numset(norm)
    scored = []  # (score, entry)
    for entry in index:
        if not _brand_ok(entry["brand"], brand):
            continue
        best = max(_guarded_score(norm, c) for c in entry["cands"])
        scored.append((best, entry))

    if not scored:
        return None
    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best_entry = scored[0]
    if best_score < min_score:
        return None

    # Number guard: if both sides carry numbers and share none, it's a different
    # pack/strength (e.g. CANROLFIN CREAM 15 GM vs 30 GM) -> refuse.
    if spel_nums and best_entry["nums"] and not (spel_nums & best_entry["nums"]):
        return None

    # Ambiguity guard: a near-tie between two products (pack variants) -> refuse.
    if len(scored) > 1 and best_score < 1.0:
        second = scored[1][0]
        if best_score - second < margin:
            return None

    return best_entry["product"]


def _enumerate_reports(data_root: Path) -> list[Path]:
    files: list[Path] = []
    for dirpath, _dirnames, filenames in os.walk(data_root):
        for name in filenames:
            if Path(name).suffix.lower() in REPORT_EXTS:
                files.append(Path(dirpath) / name)
    return sorted(files)


def collect_spellings(files: list[Path]):
    """Run extractors over every file; return {spelling: division_hint} plus failure list."""
    spellings: dict[str, str] = {}
    failures: list[tuple[str, str]] = []
    total = len(files)
    for idx, path in enumerate(files, 1):
        route, extractor = _route_for(path)
        try:
            data = path.read_bytes()
            result = extractor(data, {"filename": path.name})
        except Exception as exc:  # image-only PDF, corrupt/locked file, unreadable .xls, etc.
            failures.append((str(path), f"{type(exc).__name__}: {exc}"))
            continue

        div = _division_hint(path)
        for row in result.get("rows") or []:
            # Prefer the pre-enrichment raw spelling; fall back to the (possibly canonical) name.
            name = row.get("raw_product_name") or row.get("product_name")
            if not name:
                continue
            name = str(name).strip()
            if name and name not in spellings:
                spellings[name] = div

        if idx % 25 == 0 or idx == total:
            print(f"  ...{idx}/{total} files  (distinct spellings: {len(spellings)}, failed: {len(failures)})")
    return spellings, failures


def main() -> int:
    ap = argparse.ArgumentParser(description="Append report product spellings as synonyms in product_master.json")
    ap.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT), help="Root folder of vendor reports")
    ap.add_argument("--min-score", type=float, default=0.90, help="Min guarded score to attach a synonym")
    ap.add_argument("--margin", type=float, default=0.03,
                    help="Min score gap over the runner-up product (ambiguity guard)")
    ap.add_argument("--apply", action="store_true", help="Write both product_master.json copies (default: dry-run)")
    ap.add_argument("--dry-run", action="store_true", help="Report only, write nothing (the default)")
    ap.add_argument("--report", default=str(ROOT / "scripts" / "_synonym_unmatched.txt"),
                    help="Where to write the unmatched-spellings report")
    ap.add_argument("--cache", default=str(ROOT / "scripts" / "_synonym_spellings_cache.json"),
                    help="Where collected spellings are cached (skip the slow scan on reuse)")
    ap.add_argument("--from-cache", action="store_true",
                    help="Reuse the spellings cache instead of re-scanning the Data tree")
    args = ap.parse_args()

    data_root = Path(args.data_root)
    if not args.from_cache and not data_root.exists():
        print(f"Data root not found: {data_root}")
        return 2

    # Working copy of the catalog. Point the module singleton at it so normalize_product()
    # matches against (and stays consistent with) the spellings we append this run.
    with MASTER_PATHS[0].open(encoding="utf-8") as fh:
        catalog = json.load(fh)
    pm._PRODUCT_MASTER = catalog

    # Normalized set of everything already covered (canonical names + existing synonyms).
    covered = set()
    for product in catalog:
        covered.add(_normalize_name(product.get("canonical_name", "")))
        for syn in product.get("synonyms", []):
            covered.add(_normalize_name(syn))
    covered.discard("")

    print(f"Catalog: {len(catalog)} products, "
          f"{sum(len(p.get('synonyms', [])) for p in catalog)} synonyms")

    cache_path = Path(args.cache)
    if args.from_cache:
        if not cache_path.exists():
            print(f"No cache at {cache_path} — run once without --from-cache first.")
            return 2
        with cache_path.open(encoding="utf-8") as fh:
            cached = json.load(fh)
        spellings, failures = cached["spellings"], cached.get("failures", [])
        print(f"Loaded {len(spellings)} cached spellings from {cache_path}")
    else:
        print(f"Scanning reports under: {data_root}")
        files = _enumerate_reports(data_root)
        print(f"Found {len(files)} report files (.pdf/.xls/.xlsx)\n")
        spellings, failures = collect_spellings(files)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with cache_path.open("w", encoding="utf-8") as fh:
            json.dump({"spellings": spellings, "failures": failures}, fh, ensure_ascii=False, indent=2)
        print(f"Cached spellings to {cache_path}")

    print(f"\nExtracted {len(spellings)} distinct product spellings "
          f"({len(failures)} files failed to extract)\n")

    added = defaultdict(list)          # canonical_name -> [new synonyms]
    unmatched: dict[str, str] = {}     # plausible product, no confident match
    noise: list[str] = []              # rejected as footer/fragment/sentence noise

    index = _build_index(catalog)
    for spelling, div in sorted(spellings.items()):
        norm = _normalize_name(spelling)
        if not norm or norm in covered:
            continue                   # blank or already a canonical/synonym
        if not _is_plausible_product(spelling, norm):
            noise.append(spelling)
            continue
        product = _strict_match(norm, index, args.min_score, args.margin)
        if product is not None:
            product.setdefault("synonyms", []).append(spelling)
            covered.add(norm)
            added[product.get("canonical_name", "?")].append(spelling)
        else:
            unmatched[spelling] = div

    # ---- Report -------------------------------------------------------------
    total_added = sum(len(v) for v in added.values())
    print("=" * 64)
    print("Synonyms to add" if not args.apply else "Synonyms added")
    print("=" * 64)
    for canonical in sorted(added):
        print(f"\n{canonical}")
        for syn in sorted(added[canonical]):
            print(f"    + {syn}")
    print(f"\n{total_added} synonyms across {len(added)} products")
    print(f"{len(unmatched)} plausible names matched no product (see {args.report})")
    print(f"{len(noise)} spellings rejected as footer/fragment noise (not added)")

    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as fh:
        fh.write(f"# Unmatched product spellings (no master product >= score {args.min_score})\n")
        fh.write("# Candidates for manual seeding into product_master.json.\n")
        fh.write(f"# {len(unmatched)} spellings.\n\n")
        for spelling in sorted(unmatched):
            div = unmatched[spelling]
            fh.write(f"{spelling}\t[{div}]\n" if div else f"{spelling}\n")

    if failures:
        fail_report = Path(args.report).with_name("_synonym_failures.txt")
        with open(fail_report, "w", encoding="utf-8") as fh:
            fh.write(f"# {len(failures)} files failed to extract\n\n")
            for path, err in failures:
                fh.write(f"{path}\t{err}\n")
        print(f"{len(failures)} extraction failures logged to {fail_report}")

    # ---- Write --------------------------------------------------------------
    if not args.apply:
        print("\nDRY RUN — nothing written. Re-run with --apply to update product_master.json.")
        return 0

    if total_added == 0:
        print("\nNothing to add — catalog already covers every spelling. No files written.")
        return 0

    # Keep synonyms sorted & de-duplicated (case-insensitive) within each product.
    for product in catalog:
        seen, deduped = set(), []
        for syn in product.get("synonyms", []):
            key = syn.strip().lower()
            if key and key not in seen:
                seen.add(key)
                deduped.append(syn)
        product["synonyms"] = sorted(deduped, key=str.lower)

    payload = json.dumps(catalog, indent=2, ensure_ascii=False) + "\n"
    for master_path in MASTER_PATHS:
        master_path.parent.mkdir(parents=True, exist_ok=True)
        with master_path.open("w", encoding="utf-8") as fh:
            fh.write(payload)
        print(f"Wrote {master_path}")

    print(f"\nApplied {total_added} synonyms to {len(MASTER_PATHS)} catalog copies.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
