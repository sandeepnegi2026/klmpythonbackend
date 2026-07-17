#!/usr/bin/env python3
"""
Relocate vendor reports that were dropped into the wrong batch folder.

A vendor sometimes names a stock-&-sales export `*_party_product_*` (or a party
report `*_stock_sales_*`) and drops it under the wrong folder, so the party
extractor runs over a stock statement (or vice-versa). This script classifies each
file by its actual columns and moves the misfiled ones into the matching folder.

Classification is by header content (not filename):
  * STOCK report  = has opening AND closing stock columns (a stock statement),
                    typically without invoice/bill columns.
  * PARTY report  = has invoice/bill (+ line-item) columns and NO opening+closing pair.

Dry-run by default (lists candidates, moves nothing). Pass --apply to move files;
every move is appended to scripts/_misfiled_moved.txt so it can be undone.

This is a DATA-HYGIENE step, not a parser change (AGENTS.md): it touches no
extractor/detect/parse logic and adds no canonical synonyms for stock-only columns
that have no party field.

Usage:
  python scripts/relocate_misfiled_reports.py --batch "26 June"            # dry-run
  python scripts/relocate_misfiled_reports.py --batch "26 June" --apply    # move + log
  python scripts/relocate_misfiled_reports.py \
      --party-root "D:/.../party_wise-26 June" \
      --stock-root "D:/.../sales and stock -26 June" --apply
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]              # .../Projects/Backends
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Header detection runs before product enrichment; neutralise enrichment (the per-row
# bottleneck) so classification of a whole batch is fast.
import core.product_master as _pm
_pm.enrich_rows_with_master = lambda rows, *a, **k: rows

from extractors.party_pdf.pipeline import extract as extract_party_pdf
from extractors.party_xlsx.pipeline import extract as extract_party_xlsx
from extractors.stock_pdf.pipeline import extract as extract_stock_pdf
from extractors.stock_xlsx.pipeline import extract as extract_stock_xlsx

PROJECTS = ROOT.parent
DEFAULT_DATA_ROOT = PROJECTS.parent / "Data" / "New Data"
REPORT_EXTS = {".pdf", ".xls", ".xlsx"}
LOG_PATH = ROOT / "scripts" / "_misfiled_moved.txt"


def _extract(path: Path, report_type: str):
    is_xlsx = path.suffix.lower() in (".xls", ".xlsx")
    if report_type == "party":
        fn = extract_party_xlsx if is_xlsx else extract_party_pdf
    else:
        fn = extract_stock_xlsx if is_xlsx else extract_stock_pdf
    return fn(path.read_bytes(), {"filename": path.name})


def _header_tokens(path: Path, report_type: str) -> set[str]:
    try:
        res = _extract(path, report_type)
    except Exception:
        return set()
    return {str(h).strip().lower() for h in (res.get("headers_detected") or {})}


def _has(tokens: set[str], *subs: str) -> bool:
    return any(any(s in t for s in subs) for t in tokens)


def classify(tokens: set[str]) -> tuple[bool, bool]:
    """Return (looks_like_stock, looks_like_party) from header tokens."""
    open_ = _has(tokens, "opening", "opstk", "op stk", "openstk", "ostk") or {"op", "open"} & tokens
    close_ = (
        _has(tokens, "closing", "closestk", "cls stk", "clstk", "closestock", "curstk", "qoh", "cls.stk")
        or {"cl", "clos"} & tokens
    )
    invoice = _has(tokens, "inv no", "invno", "bill no", "billno", "bill date", "billdate", "invoice", "feedno", "feeddate")
    looks_stock = bool(open_) and bool(close_)
    looks_party = bool(invoice) and not looks_stock
    return looks_stock, looks_party


def _stock_rows_populated(sres) -> bool:
    """True when the stock route produced rows that actually carry BOTH an
    opening and a closing stock value — the structural fingerprint of a stock
    statement, and robust for POSITIONAL parsers that emit no header tokens for
    ``classify`` to read.
    """
    rows = sres.get("rows") or []

    def _num(v) -> bool:
        try:
            return float(v) != 0.0
        except (TypeError, ValueError):
            return False

    has_open = any(_num(r.get("opening_stock")) for r in rows)
    has_close = any(_num(r.get("closing_stock")) for r in rows)
    return has_open and has_close


def verdict(path: Path) -> str:
    """Classify a report by its CONTENT, consulting BOTH routes. Returns
    'party', 'stock', or 'unknown'.

    A file is 'party' only when the party route yields rows that actually
    populate ``party_name`` on at least one row. Row count alone is NOT enough:
    the party ``tabular`` fallback will happily lift product rows off a stock
    statement (which has no customer column), leaving every ``party_name`` blank
    — those files then RED with MISSING_REQUIRED_FIELD:party_name yet the old
    row-count test declared them 'party' and never relocated them. When the
    party route is empty OR party-name-less, we consult the stock route; a file
    that extracts rows AND shows opening+closing stock (via header tokens OR
    populated open/close values) is a stock statement misfiled into the party
    folder. Symmetric for the reverse.
    """
    try:
        pres = _extract(path, "party")
    except Exception:
        pres = {}
    prows = pres.get("rows") or []
    if any(str(r.get("party_name") or "").strip() for r in prows):
        return "party"
    try:
        sres = _extract(path, "stock")
    except Exception:
        sres = {}
    s_tokens = {str(h).strip().lower() for h in (sres.get("headers_detected") or {})}
    s_stock, _ = classify(s_tokens)
    if (len(sres.get("rows") or []) > 0) and (s_stock or _stock_rows_populated(sres)):
        return "stock"
    return "unknown"


def _resolve_roots(args) -> tuple[Path, Path]:
    if args.party_root and args.stock_root:
        return Path(args.party_root), Path(args.stock_root)
    if not args.batch:
        sys.exit("Provide --batch <DATE> or both --party-root and --stock-root")
    base = Path(args.data_root) / args.batch
    return base / f"party_wise-{args.batch}", base / f"sales and stock -{args.batch}"


def _enumerate(root: Path) -> list[Path]:
    files: list[Path] = []
    for dirpath, _d, names in os.walk(root):
        for n in names:
            if Path(n).suffix.lower() in REPORT_EXTS:
                files.append(Path(dirpath) / n)
    return sorted(files)


def _dest_for(src: Path, src_root: Path, dst_root: Path) -> Path:
    # Preserve the Excel/Pdf (or any) subfolder structure under the destination root.
    rel = src.relative_to(src_root)
    return dst_root / rel


def _same_content(a: Path, b: Path) -> bool:
    """True when two files are the same report: byte-identical, or (for the same
    export re-saved with different bytes) yielding the same extracted rows. Used
    to safely retire a misfiled duplicate whose correct-folder twin already
    exists — without ever discarding a genuinely different same-named file.
    """
    try:
        if a.read_bytes() == b.read_bytes():
            return True
    except OSError:
        return False

    def _sig(path: Path):
        for rt in ("stock", "party"):
            try:
                rows = _extract(path, rt).get("rows") or []
            except Exception:
                rows = []
            if rows:
                names = sorted(str(r.get("product_name") or "") for r in rows)
                return (rt, len(rows), tuple(names))
        return None

    sa, sb = _sig(a), _sig(b)
    return sa is not None and sa == sb


def _find_pairs(tree_root: Path) -> list[tuple[Path, Path]]:
    """Walk ``tree_root`` and pair every sibling 'Party report'/'Stock report'
    folder (same parent). Handles the per-vendor Failed-1 layout where each
    vendor owns its own Party/Stock folder pair, rather than one global pair.
    """
    party_dirs: dict[Path, Path] = {}
    stock_dirs: dict[Path, Path] = {}
    for dirpath, dirnames, _n in os.walk(tree_root):
        for d in dirnames:
            low = d.strip().lower()
            parent = Path(dirpath)
            if low in ("party report", "party_report", "party"):
                party_dirs[parent] = parent / d
            elif low in ("stock report", "stock_report", "stock"):
                stock_dirs[parent] = parent / d
    pairs = []
    for parent, pdir in party_dirs.items():
        sdir = stock_dirs.get(parent)
        if sdir is not None:
            pairs.append((pdir, sdir))
    return sorted(pairs)


def _fails_in_slot(path: Path, report_type: str) -> bool:
    """True only when the file RED-fails in its CURRENT folder's route — the sole
    justification for relocating it. A file that already extracts GREEN/AMBER in
    its slot is being handled correctly and must never be moved, even if the
    other route's tabular fallback spuriously reports a party_name off a division
    band (the KLM multi-division stock grids trip exactly that false positive).
    """
    try:
        res = _extract(path, report_type)
    except Exception:
        return True  # can't even extract here -> a genuine candidate to re-route
    try:
        from core.quality import build_quality
        bucket = build_quality(res, report_type).get("triage", {}).get("bucket")
    except Exception:
        return False
    return bucket == "RED"


def _collect_moves(party_root: Path, stock_root: Path) -> list[tuple[Path, Path, str]]:
    moves: list[tuple[Path, Path, str]] = []
    # Stock statements sitting in the party folder (party route yields no
    # party_name; stock route reconstructs opening+closing). Only relocate when
    # the party slot actually fails — a GREEN/AMBER party file stays put.
    for f in _enumerate(party_root):
        if _fails_in_slot(f, "party") and verdict(f) == "stock":
            moves.append((f, _dest_for(f, party_root, stock_root), "stock-report-in-party"))
    # Party reports sitting in the stock folder.
    for f in _enumerate(stock_root):
        if _fails_in_slot(f, "stock") and verdict(f) == "party":
            moves.append((f, _dest_for(f, stock_root, party_root), "party-report-in-stock"))
    return moves


def main() -> int:
    ap = argparse.ArgumentParser(description="Relocate misfiled party/stock reports")
    ap.add_argument("--batch", help='Batch folder name under New Data, e.g. "26 June"')
    ap.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT), help="Parent of batch folders")
    ap.add_argument("--party-root", help="Explicit party_wise folder")
    ap.add_argument("--stock-root", help="Explicit sales-and-stock folder")
    ap.add_argument("--tree-root", help="Walk a tree; pair every sibling 'Party report'/'Stock report' folder")
    ap.add_argument("--apply", action="store_true", help="Move files (default: dry-run)")
    args = ap.parse_args()

    moves: list[tuple[Path, Path, str]] = []  # (src, dst, reason)

    if args.tree_root:
        tree_root = Path(args.tree_root)
        if not tree_root.exists():
            sys.exit(f"tree-root not found: {tree_root}")
        pairs = _find_pairs(tree_root)
        print(f"Found {len(pairs)} Party/Stock folder pair(s) under {tree_root.name}")
        for pdir, sdir in pairs:
            moves.extend(_collect_moves(pdir, sdir))
    else:
        party_root, stock_root = _resolve_roots(args)
        for label, root in (("party", party_root), ("stock", stock_root)):
            if not root.exists():
                print(f"WARNING: {label} root not found: {root}")
        moves = _collect_moves(party_root, stock_root)

    print("=" * 72)
    print(f"Misfiled candidates: {len(moves)}  ({'APPLY' if args.apply else 'DRY-RUN'})")
    print("=" * 72)
    for src, dst, reason in moves:
        print(f"  [{reason}] {src.name}")
        print(f"      -> {dst}")

    if not args.apply:
        print("\nDRY-RUN — nothing moved. Re-run with --apply to relocate.")
        return 0

    if not moves:
        print("\nNothing to move.")
        return 0

    quarantine_root = Path(args.tree_root) / "_misfiled_duplicates" if args.tree_root else None

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    moved = quarantined = 0
    with LOG_PATH.open("a", encoding="utf-8") as log:
        for src, dst, reason in moves:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists():
                # The vendor uploaded the same report to BOTH slots. The copy
                # already in the correct folder extracts fine; the misfiled copy
                # is a redundant duplicate. Only retire it when content matches
                # (byte-identical, or same extracted rows) — never overwrite or
                # drop a genuinely different file that merely shares a name.
                if _same_content(src, dst) and quarantine_root is not None:
                    q = quarantine_root / src.parent.name / src.name
                    q.parent.mkdir(parents=True, exist_ok=True)
                    if not q.exists():
                        shutil.move(str(src), str(q))
                        log.write(f"duplicate-of-correct-copy\t{src}\t{q}\n")
                        quarantined += 1
                        print(f"  DUP (correct copy already at dst) -> quarantined: {src.name}")
                    else:
                        print(f"  SKIP (quarantine exists): {q}")
                else:
                    print(f"  SKIP (different file, same name): {dst}")
                continue
            shutil.move(str(src), str(dst))
            log.write(f"{reason}\t{src}\t{dst}\n")
            moved += 1
    print(f"\nMoved {moved}/{len(moves)} files; quarantined {quarantined} duplicate(s). "
          f"Log appended to {LOG_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
