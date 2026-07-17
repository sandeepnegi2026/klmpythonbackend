#!/usr/bin/env python3
"""
Regression test runner for pharma report extractors.

Compares extraction metrics against saved baselines so parser changes do not
silently break already-working vendor files.

Usage:
  python scripts/regression_test.py                  # run all suites with baselines
  python scripts/regression_test.py --suite party_cg_pdf
  python scripts/regression_test.py --update         # refresh baselines (intentional change)
  python scripts/regression_test.py --list-suites
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from extractors import party_pdf, party_xlsx, stock_pdf, stock_xlsx

MANIFEST_PATH = ROOT / "tests" / "regression_manifest.json"
BASELINES_DIR = ROOT / "tests" / "baselines"

ROUTES = {
    "party_pdf": party_pdf.extract,
    "party_xlsx": party_xlsx.extract,
    "stock_pdf": stock_pdf.extract,
    "stock_xlsx": stock_xlsx.extract,
}


def _load_manifest() -> dict:
    with MANIFEST_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def _resolve_glob(reports_root: Path, pattern: str) -> list[Path]:
    """Resolve manifest glob like 'Party Wise/CG/*.{pdf,PDF}'."""
    if "*." in pattern and "{" in pattern and "}" in pattern:
        head, brace_part = pattern.split("*.", 1)
        exts = [e.strip().lstrip(".") for e in brace_part.strip("{}").split(",")]
        base = reports_root / head.rstrip("/")
        if not base.exists():
            return []
        files: list[Path] = []
        for ext in exts:
            files.extend(base.glob(f"*.{ext}"))
        return sorted({p.resolve() for p in files if p.is_file()})

    target = reports_root / pattern
    if target.is_dir():
        return sorted(p.resolve() for p in target.iterdir() if p.is_file())
    parent = target.parent
    if parent.exists():
        return sorted(p.resolve() for p in parent.glob(target.name) if p.is_file())
    return []


def _resolve_prefixed_vendor(reports_root: Path, rel: str) -> Path | None:
    """Fallback for New_Data curated files when the vendor folder was renamed.

    The user marks a vendor's folder done by prefixing it (Ok-/OK-/ok-/0k-/"..-"),
    which breaks the exact "New_Data/<vendor>/..." path but always preserves the
    vendor name as a suffix. Match the folder by that suffix and rebuild the path.
    """
    parts = rel.replace("\\", "/").split("/")
    if "New_Data" not in parts:
        return None
    i = parts.index("New_Data")
    if i + 2 >= len(parts):
        return None
    vendor, tail = parts[i + 1], parts[i + 2:]
    newdata_dir = (reports_root / "/".join(parts[: i + 1])).resolve()
    if not newdata_dir.is_dir():
        return None
    for d in sorted(newdata_dir.iterdir()):
        if d.is_dir() and (d.name == vendor or d.name.endswith(vendor)):
            cand = d.joinpath(*tail)
            if cand.is_file():
                return cand.resolve()
    return None


def _resolve_files(reports_root: Path, rel_paths: list[str]) -> list[Path]:
    """Resolve an explicit, curated list of files (relative to reports_root).

    Used by date-wise New Data suites that test only the specific sample files
    we have verified, instead of globbing an entire (large) batch folder.
    """
    out: list[Path] = []
    for rel in rel_paths:
        p = (reports_root / rel).resolve()
        if not p.is_file():
            alt = _resolve_prefixed_vendor(reports_root, rel)
            if alt is not None:
                p = alt
        if p.is_file():
            out.append(p)
        else:
            print(f"  MISSING FILE: {rel}")
    return sorted(set(out))


def _num(value):
    text = str(value or "").replace(",", "").strip()
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def _party_metrics(rows: list[dict]) -> dict:
    parties = sorted({str(r.get("party_name") or "").strip() for r in rows if str(r.get("party_name") or "").strip()})
    areas = sorted({str(r.get("party_location") or "").strip() for r in rows if str(r.get("party_location") or "").strip()})
    products = sorted({str(r.get("product_name") or "").strip() for r in rows if str(r.get("product_name") or "").strip()})
    qty_total = sum(_num(r.get("qty")) for r in rows)
    amount_total = sum(_num(r.get("amount")) for r in rows)
    return {
        "party_count": len(parties),
        "area_count": len(areas),
        "product_count": len(products),
        "sample_parties": parties[:5],
        "sample_products": products[:5],
        "qty_total": round(qty_total, 2),
        "amount_total": round(amount_total, 2),
        # Rate-column fingerprints. rate/purchase_rate carry no additive meaning, but the
        # rounded sum is a checksum that trips if a header re-maps — e.g. "Purc rate" stealing
        # `rate` from "Sale rate", or a re-added `sales_rate` field draining `rate`. These
        # fields are otherwise absent from the snapshot, so mapping regressions slip through.
        "rate_total": round(sum(_num(r.get("rate")) for r in rows), 2),
        "purchase_rate_total": round(sum(_num(r.get("purchase_rate")) for r in rows), 2),
    }



def _stock_metrics(rows: list[dict]) -> dict:
    products = sorted({str(r.get("product_name") or "").strip() for r in rows if str(r.get("product_name") or "").strip()})
    closing_total = sum(_num(r.get("closing_stock")) for r in rows)
    return {
        "product_count": len(products),
        "sample_products": products[:5],
        "closing_stock_total": round(closing_total, 2),
        # Rate-column fingerprint (see _party_metrics) — guards stock rate re-mapping.
        "rate_total": round(sum(_num(r.get("rate")) for r in rows), 2),
    }


def _snapshot(route: str, path: Path) -> dict:
    file_bytes = path.read_bytes()
    settings = {"filename": path.name}
    result = ROUTES[route](file_bytes, settings)
    rows = result.get("rows") or []
    snap = {
        "file": path.name,
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
    return snap


def _baseline_path(suite: str, filename: str) -> Path:
    safe = filename.replace("/", "_").replace("\\", "_")
    return BASELINES_DIR / suite / f"{safe}.json"


def _compare(expected: dict, actual: dict) -> list[str]:
    diffs: list[str] = []
    keys = sorted(set(expected) | set(actual))
    for key in keys:
        if key in {"file", "route"}:
            continue
        if expected.get(key) != actual.get(key):
            diffs.append(f"{key}: expected {expected.get(key)!r}, got {actual.get(key)!r}")
    return diffs


def run_suite(suite: str, cfg: dict, reports_root: Path, update: bool,
              exclude_contains: list | None = None) -> tuple[int, int, int]:
    route = cfg["route"]
    if "files" in cfg:
        files = _resolve_files(reports_root, cfg["files"])
    else:
        files = _resolve_glob(reports_root, cfg["glob"])
    # Optional per-suite exact-basename exclusions.
    exclude = set(cfg.get("exclude") or [])
    if exclude:
        files = [f for f in files if f.name not in exclude]
    # Global substring exclusions (manifest "exclude_contains"), case-insensitive on
    # basename — keeps OCR/"need review" files out of regression per project rule so a
    # stray one dropped in a data folder can never silently rejoin the suite.
    pats = [s.lower() for s in (exclude_contains or [])]
    if pats:
        before = len(files)
        files = [f for f in files if not any(p in f.name.lower() for p in pats)]
        if before - len(files):
            print(f"  (excluded {before - len(files)} need-review/uncertain file(s))")
    if not files:
        where = f"{len(cfg['files'])} listed file(s)" if "files" in cfg else str(reports_root / cfg["glob"].split("{")[0])
        print(f"  SKIP {suite}: no files ({where})")
        return 0, 0, 0

    passed = failed = skipped = 0
    for path in files:
        actual = _snapshot(route, path)
        baseline_file = _baseline_path(suite, path.name)

        if update:
            baseline_file.parent.mkdir(parents=True, exist_ok=True)
            with baseline_file.open("w", encoding="utf-8") as fh:
                json.dump(actual, fh, indent=2, ensure_ascii=False)
            print(f"  UPDATED {path.name}")
            passed += 1
            continue

        if not baseline_file.exists():
            print(f"  MISSING BASELINE {path.name} (run with --update)")
            skipped += 1
            continue

        with baseline_file.open(encoding="utf-8") as fh:
            expected = json.load(fh)
        diffs = _compare(expected, actual)
        if diffs:
            failed += 1
            print(f"  FAIL {path.name}")
            for diff in diffs:
                print(f"       - {diff}")
        else:
            passed += 1
            print(f"  OK   {path.name} rows={actual['row_count']}")

    return passed, failed, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description="Regression tests for report extractors")
    parser.add_argument("--suite", action="append", help="Run only named suite(s) from manifest")
    parser.add_argument("--update", action="store_true", help="Write/refresh baseline snapshots")
    parser.add_argument("--list-suites", action="store_true", help="List configured suites")
    args = parser.parse_args()

    manifest = _load_manifest()
    reports_root = (ROOT / manifest.get("reports_root", "../..")).resolve()
    suites: dict = manifest["suites"]
    exclude_contains = manifest.get("exclude_contains") or []

    if args.list_suites:
        for name, cfg in suites.items():
            print(f"{name:20} {cfg['route']:12} {cfg['description']}")
        print(f"\nReports root: {reports_root}")
        return 0

    selected = args.suite or list(suites.keys())
    unknown = [s for s in selected if s not in suites]
    if unknown:
        print(f"Unknown suite(s): {', '.join(unknown)}")
        return 2

    print(f"Reports root: {reports_root}")
    print(f"Mode: {'UPDATE baselines' if args.update else 'COMPARE to baselines'}\n")

    total_pass = total_fail = total_skip = 0
    for suite in selected:
        print(f"[{suite}]")
        p, f, s = run_suite(suite, suites[suite], reports_root, args.update, exclude_contains)
        total_pass += p
        total_fail += f
        total_skip += s
        print()

    print("=" * 60)
    print(f"Passed: {total_pass}  Failed: {total_fail}  Skipped (no baseline): {total_skip}")
    if args.update:
        print("Baselines updated. Commit tests/baselines/ if changes were intentional.")
        return 0
    return 1 if total_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
