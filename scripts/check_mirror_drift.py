#!/usr/bin/env python3
"""Fail CI when the extraction ENGINE drifts between the two trees.

The extraction engine -- the ``core/`` and ``extractors/`` packages -- is mirrored
across the runtime tree (Backends) and the dev/staging tree (Python-Service-UI)
and MUST stay byte-identical. New vendor layouts are staged in PSUI first, so a
short, EXPLICIT allowlist lets a not-yet-mirrored file pass; everything else that
diverges is a drift and fails the check.

Usage:
    python check_mirror_drift.py                 # uses the default tree paths
    python check_mirror_drift.py A_ROOT B_ROOT   # compare two explicit roots
    python check_mirror_drift.py --json          # machine-readable report
    python check_mirror_drift.py --allow path1,path2   # extra staged allowances

Exit code 0 = in sync (modulo allowlist); 1 = drift detected; 2 = bad invocation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

# --- Defaults ---------------------------------------------------------------
# Resolve relative to this file's grandparent so it works regardless of cwd:
#   <projects>/<tree>/scripts/check_mirror_drift.py  ->  <projects>
_HERE = Path(__file__).resolve()
_PROJECTS = _HERE.parents[2] if len(_HERE.parents) >= 3 else _HERE.parent
DEFAULT_A = _PROJECTS / "Backends"
DEFAULT_B = _PROJECTS / "Python-Service-UI"

# Directories that constitute the mirror contract (relative to each tree root).
MIRRORED_DIRS = ("core", "extractors")

# Individual material files that must also stay in sync but live OUTSIDE the
# mirrored dirs. data/product_master.json is the live enrichment catalog -- the DEV
# sync tooling (scripts/sync_product_master.py) declares it a two-copy mirror, and
# drift there silently changes extraction output. Dated .bak/backup snapshots in
# data/ are deliberately NOT listed (they legitimately differ and are never loaded).
MIRRORED_FILES = ("data/product_master.json",)

# The VERIFICATION TOOLCHAIN also lives in both trees and must stay byte-identical
# (Backends imports these; a drift here silently breaks its tests). Historically
# uncovered — that is exactly how `scripts/batch_extract.py` lost `line_ledger.py`
# from its cache signature undetected (2026-07-21). Reported on their OWN line so
# the engine count (the "identical: 477" pass bar) is unchanged; any drift here
# still FAILS the check. run_full_suite.py's S5 also cross-checks these.
MIRRORED_TOOLCHAIN = (
    "scripts/batch_extract.py", "scripts/batch_core.py", "scripts/render_dashboard.py",
    "scripts/regression_test.py", "scripts/run_full_suite.py",
    "tests/test_triage.py", "tests/test_line_ledger.py", "tests/test_pack_match.py",
)

# Extensions that are part of the engine. .py is the code; the data extensions
# catch bundled catalogs/synonyms/schemas whose drift silently changes output.
MIRRORED_EXTS = (".py", ".json", ".txt", ".csv", ".yaml", ".yml")

# Path fragments never compared (build/cache artifacts).
EXCLUDE_FRAGMENTS = ("__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache")

# EXPLICIT staged allowlist: files known to be PSUI-first and not yet mirrored.
# Keep this SHORT and dated; a growing list means the mirror is rotting.
# Format: engine-relative POSIX paths (e.g. "extractors/party_pdf/layouts/foo.py").
DEFAULT_ALLOWLIST: set[str] = {
    # e.g. "extractors/party_pdf/layouts/klm_group_vs_customer_custbanded.py",  # staged 2026-07-19
}


def _excluded(p: Path) -> bool:
    parts = set(p.parts)
    return any(frag in parts for frag in EXCLUDE_FRAGMENTS)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def inventory(root: Path, files: tuple[str, ...] = MIRRORED_FILES,
              dirs: tuple[str, ...] = MIRRORED_DIRS) -> dict[str, str]:
    """Engine-relative POSIX path -> sha256, over the given dirs + files/exts."""
    out: dict[str, str] = {}
    for sub in dirs:
        base = root / sub
        if not base.is_dir():
            continue
        for f in base.rglob("*"):
            if not f.is_file() or _excluded(f) or f.suffix.lower() not in MIRRORED_EXTS:
                continue
            rel = f.relative_to(root).as_posix()
            out[rel] = _sha256(f)
    for rel in files:
        f = root / rel
        if f.is_file():
            out[rel] = _sha256(f)
    return out


def _diff(a: dict, b: dict, allowlist: set[str]):
    only_a = sorted(k for k in a if k not in b)
    only_b = sorted(k for k in b if k not in a)
    drifted = sorted(k for k in a if k in b and a[k] != b[k])

    def _flag(paths: list[str]) -> list[dict]:
        return [{"path": p, "allowed": p in allowlist} for p in paths]

    findings = _flag(only_a) + _flag(only_b) + _flag(drifted)
    unexpected = [f["path"] for f in findings if not f["allowed"]]
    identical = sum(1 for k in a if k in b and a[k] == b[k])
    return _flag(only_a), _flag(only_b), _flag(drifted), unexpected, identical


def audit(a_root: Path, b_root: Path, allowlist: set[str]) -> dict:
    a, b = inventory(a_root), inventory(b_root)
    only_a, only_b, drifted, unexpected, identical = _diff(a, b, allowlist)

    # Toolchain (scripts/tests that live in both trees) — reported separately so
    # the engine "identical" count is untouched, but its drift still fails.
    ta = inventory(a_root, files=MIRRORED_TOOLCHAIN, dirs=())
    tb = inventory(b_root, files=MIRRORED_TOOLCHAIN, dirs=())
    t_only_a, t_only_b, t_drift, t_unexpected, t_identical = _diff(ta, tb, allowlist)

    return {
        "a_root": str(a_root),
        "b_root": str(b_root),
        "a_count": len(a),
        "b_count": len(b),
        "identical": identical,
        "only_in_a": only_a,
        "only_in_b": only_b,
        "content_drift": drifted,
        "toolchain_count": len(ta),
        "toolchain_identical": t_identical,
        "toolchain_only_in_a": t_only_a,
        "toolchain_only_in_b": t_only_b,
        "toolchain_drift": t_drift,
        "unexpected_drift": unexpected + t_unexpected,
        "in_sync": not unexpected and not t_unexpected,
    }


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("roots", nargs="*", help="Optional A_ROOT B_ROOT (defaults: Backends, Python-Service-UI)")
    ap.add_argument("--json", action="store_true", help="machine-readable report")
    ap.add_argument("--allow", default="", help="comma-separated extra allowlisted engine-relative paths")
    args = ap.parse_args(argv)

    if len(args.roots) == 2:
        a_root, b_root = Path(args.roots[0]), Path(args.roots[1])
    elif not args.roots:
        a_root, b_root = DEFAULT_A, DEFAULT_B
    else:
        print("error: provide either 0 or 2 root paths", file=sys.stderr)
        return 2
    for r in (a_root, b_root):
        if not r.is_dir():
            print(f"error: not a directory: {r}", file=sys.stderr)
            return 2

    allowlist = set(DEFAULT_ALLOWLIST)
    allowlist.update(x.strip() for x in args.allow.split(",") if x.strip())

    report = audit(a_root, b_root, allowlist)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"A: {report['a_root']}  ({report['a_count']} engine files)")
        print(f"B: {report['b_root']}  ({report['b_count']} engine files)")
        print(f"identical: {report['identical']}")
        print(f"toolchain (scripts/tests): {report['toolchain_identical']}/"
              f"{report['toolchain_count']} identical")
        for key, title in (("only_in_a", "ONLY in A"),
                           ("only_in_b", "ONLY in B"),
                           ("content_drift", "CONTENT DRIFT"),
                           ("toolchain_only_in_a", "TOOLCHAIN ONLY in A"),
                           ("toolchain_only_in_b", "TOOLCHAIN ONLY in B"),
                           ("toolchain_drift", "TOOLCHAIN DRIFT")):
            rows = report[key]
            if rows:
                print(f"\n{title} ({len(rows)}):")
                for row in rows:
                    tag = "  [allowed]" if row["allowed"] else "  <-- DRIFT"
                    print(f"  {row['path']}{tag}")
        if report["in_sync"]:
            print("\nRESULT: engine in sync (allowlisted staging ignored).")
        else:
            print(f"\nRESULT: {len(report['unexpected_drift'])} unexpected drift(s) -- FAIL.")

    return 0 if report["in_sync"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
