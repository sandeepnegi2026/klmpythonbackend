#!/usr/bin/env python3
"""
Sync product_master.json from the local Supabase DB (the source of truth).

The DB table `products_master` (joined to `divisions`) holds the LATEST product
name, pack and division. `product_master.json` (two identical mirrors used by the
Python/Streamlit extractor's matcher) holds the same products PLUS the synonym
spellings harvested from real reports by build_product_synonyms.py.

This script makes the two consistent on the fields the DB owns:

    name (canonical_name)  : DB  -> JSON   (DB Title Case wins)
    pack (pack_size)       : DB  -> JSON
    division               : DB  -> JSON   (divisions.code)
    code (product code)    : DB  -> JSON   (stable join key for future syncs)
    synonyms               : preserved from the existing JSON, re-attached by
                             (normalized_name, division)

Synonyms are NOT pulled from the DB here (the DB owns them in `product_aliases`,
seeded the other way by gen_product_aliases_migration.py). This script never
invents or drops products: it asserts the DB and JSON product sets match 1:1 and
reports any drift instead of silently losing synonyms.

It writes BOTH mirrors identically, matching build_product_synonyms.py's output
style (synonyms sorted case-insensitively, JSON indent=2, trailing newline).

DB access is via the `psql` CLI (no Python driver needed). Local defaults match
the Supabase dev stack; override with PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE.

Usage:
  python scripts/sync_product_master.py            # dry-run: report drift, write nothing
  python scripts/sync_product_master.py --apply    # rewrite both product_master.json copies
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]              # .../Projects/Backends
PROJECTS = ROOT.parent                                  # .../Projects

# Keep the two mirrors byte-identical (same list build_product_synonyms.py uses).
MASTER_PATHS = [
    PROJECTS / "Backends" / "data" / "product_master.json",
    PROJECTS / "Python-Service-UI" / "data" / "product_master.json",
]


def _normalize_name(name: str) -> str:
    """Identical to core.product_master._normalize_name and the edge function's
    normalizeName(): lower-case, non-alphanumeric -> space, collapse, strip."""
    if not name:
        return ""
    text = re.sub(r"[^a-zA-Z0-9]+", " ", str(name).lower())
    return re.sub(r"\s+", " ", text).strip()


def _precise_key(name: str) -> str:
    """Case/space-insensitive but PUNCTUATION-preserving, so near-identical
    products that only differ by a trailing '.' (e.g. 'Klm C 1000' vs
    'Klm C 1000.') stay distinct where _normalize_name would merge them."""
    return re.sub(r"\s+", " ", str(name or "").strip().lower())


def _psql_env() -> dict:
    env = dict(os.environ)
    env.setdefault("PGHOST", "127.0.0.1")
    env.setdefault("PGPORT", "54322")
    env.setdefault("PGUSER", "postgres")
    env.setdefault("PGPASSWORD", "postgres")
    env.setdefault("PGDATABASE", "postgres")
    return env


def fetch_db_products(psql: str) -> list[dict]:
    """Return [{code, canonical_name, normalized_name, pack, division}] from the DB."""
    sql = (
        "SELECT COALESCE(json_agg(json_build_object("
        "  'code', pm.code,"
        "  'canonical_name', pm.canonical_name,"
        "  'normalized_name', pm.normalized_name,"
        "  'pack', COALESCE(pm.pack_size, ''),"
        "  'division', d.code"
        ") ORDER BY d.code, pm.normalized_name), '[]'::json) "
        "FROM products_master pm JOIN divisions d ON d.id = pm.division_id;"
    )
    proc = subprocess.run(
        [psql, "-t", "-A", "-c", sql],
        env=_psql_env(), capture_output=True, text=True,
    )
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        raise SystemExit(f"psql failed (exit {proc.returncode}). Is the local Supabase DB up?")
    return json.loads(proc.stdout.strip() or "[]")


def load_existing_synonyms() -> tuple[dict, dict, list]:
    """From the current JSON, build a precise map and a loose map of
    key -> synonyms[], plus the raw catalog (for drift reporting).

    precise key = _precise_key(canonical_name) + division  (punctuation kept)
    loose key   = _normalize_name(canonical_name) + division (fallback)
    """
    src = MASTER_PATHS[0]
    with src.open(encoding="utf-8") as fh:
        catalog = json.load(fh)
    precise_map: dict[tuple[str, str], list] = {}
    loose_map: dict[tuple[str, str], list] = {}
    for p in catalog:
        div = p.get("division", "")
        syns = list(p.get("synonyms", []) or [])
        precise_map[(_precise_key(p.get("canonical_name", "")), div)] = syns
        loose_map[(_normalize_name(p.get("canonical_name", "")), div)] = syns
    return precise_map, loose_map, catalog


def _dedupe_sorted(syns: list) -> list:
    seen, out = set(), []
    for s in syns:
        k = (s or "").strip().lower()
        if k and k not in seen:
            seen.add(k)
            out.append(s)
    return sorted(out, key=str.lower)


def build_catalog(db_products: list[dict], precise_map: dict, loose_map: dict) -> tuple[list, dict]:
    """Produce the new catalog (DB name/pack/division + preserved synonyms).

    Attach synonyms by precise key first; fall back to the loose (normalized)
    key only when that loose key is UNAMBIGUOUS on the DB side, so a collapsed
    pair like 'Klm C 1000' / 'Klm C 1000.' never cross-contaminates."""
    # Loose keys that map to >1 DB product are ambiguous — never use the fallback.
    loose_counts: dict[tuple[str, str], int] = {}
    for p in db_products:
        loose_counts[(p["normalized_name"], p["division"])] = \
            loose_counts.get((p["normalized_name"], p["division"]), 0) + 1

    used_precise: set = set()
    out = []
    stats = {"products": len(db_products), "with_synonyms": 0,
             "synonyms_total": 0, "no_synonym_match": [], "via_loose": 0}
    for p in db_products:
        pk = (_precise_key(p["canonical_name"]), p["division"])
        lk = (p["normalized_name"], p["division"])
        if pk in precise_map:
            syns = precise_map[pk]
            used_precise.add(pk)
        elif loose_counts.get(lk, 0) == 1 and lk in loose_map:
            syns = loose_map[lk]
            stats["via_loose"] += 1
        else:
            syns = []
        syns = _dedupe_sorted(syns)
        if syns:
            stats["with_synonyms"] += 1
            stats["synonyms_total"] += len(syns)
        else:
            stats["no_synonym_match"].append((p["canonical_name"], p["division"]))
        out.append({
            "code": p["code"],
            "canonical_name": p["canonical_name"],
            "pack": p["pack"],
            "division": p["division"],
            "synonyms": syns,
        })
    # Any precise JSON key we never consumed = synonyms that failed to attach.
    stats["orphaned_precise"] = [k for k in precise_map if k not in used_precise]
    return out, stats


def report_drift(db_products: list[dict], existing_catalog: list) -> int:
    """Print products present on one side only (would orphan synonyms). Returns
    the count of JSON-only entries (the dangerous direction)."""
    db_keys = {(p["normalized_name"], p["division"]) for p in db_products}
    json_keys = {(_normalize_name(p.get("canonical_name", "")), p.get("division", ""))
                 for p in existing_catalog}
    db_only = db_keys - json_keys
    json_only = json_keys - db_keys
    print(f"DB products: {len(db_keys)}   JSON products: {len(json_keys)}")
    print(f"In DB, new to JSON (no synonyms yet): {len(db_only)}")
    for k in sorted(db_only)[:20]:
        print(f"    + {k[1]} / {k[0]}")
    print(f"In JSON, not in DB (synonyms would be DROPPED): {len(json_only)}")
    for k in sorted(json_only)[:20]:
        print(f"    ! {k[1]} / {k[0]}")
    return len(json_only)


def main() -> int:
    ap = argparse.ArgumentParser(description="Sync product_master.json name/pack/division from the local DB")
    ap.add_argument("--apply", action="store_true", help="Write both product_master.json copies (default: dry-run)")
    ap.add_argument("--psql", default="psql", help="psql executable (default: psql on PATH)")
    ap.add_argument("--allow-drop", action="store_true",
                    help="Proceed even if JSON-only products would lose synonyms (default: refuse)")
    args = ap.parse_args()

    db_products = fetch_db_products(args.psql)
    if not db_products:
        print("No products returned from DB — aborting.")
        return 2

    precise_map, loose_map, existing_catalog = load_existing_synonyms()

    print("=" * 64)
    print("Drift check")
    print("=" * 64)
    json_only = report_drift(db_products, existing_catalog)

    new_catalog, stats = build_catalog(db_products, precise_map, loose_map)
    print()
    print(f"Built catalog: {stats['products']} products, "
          f"{stats['with_synonyms']} with synonyms, "
          f"{stats['synonyms_total']} synonyms preserved "
          f"({stats['via_loose']} attached via loose fallback)")
    if stats["no_synonym_match"]:
        print(f"{len(stats['no_synonym_match'])} products carry no synonyms "
              f"(brand-new or never seen in a report).")

    orphaned = stats["orphaned_precise"]
    if orphaned:
        print(f"\nWARNING: {len(orphaned)} JSON products' synonyms could not be "
              f"attached to any DB product (name drift). Examples:")
        for k in orphaned[:20]:
            print(f"    ! {k[1]} / {k[0]}")

    if (json_only or orphaned) and not args.allow_drop:
        print(f"\nREFUSING to write: synonyms would be lost "
              f"({json_only} JSON-only products, {len(orphaned)} unattachable). "
              f"Re-run with --allow-drop if that's intended.")
        return 3

    if not args.apply:
        print("\nDRY RUN — nothing written. Re-run with --apply to update both copies.")
        return 0

    payload = json.dumps(new_catalog, indent=2, ensure_ascii=False) + "\n"
    for path in MASTER_PATHS:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            fh.write(payload)
        print(f"Wrote {path}")
    print(f"\nSynced {stats['products']} products to {len(MASTER_PATHS)} catalog copies.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
