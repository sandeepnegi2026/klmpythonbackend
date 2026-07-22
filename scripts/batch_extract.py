#!/usr/bin/env python3
"""
Shared single-extraction layer — extract every file ONCE, reuse everywhere.

Today each phase (triage, header scan, product harvest, regression) re-parses the
SAME file independently, so a full pipeline pays 4-5x the extraction cost. This
module makes the extraction a shared, cached, parallel step: every consumer reads
the SAME `extract()` result instead of calling the engine itself.

  extract_batch(jobs, workers=N) -> {abs_path: result}

A result is cached on disk under `_extract_cache/<route>/<sha1>.json`, keyed by the
file's SHA1 + an extraction code-signature. The signature fingerprints only the
modules that actually affect extraction (`extractors/` + the four core modules the
pipelines import). So:

  * a NEW or CHANGED file re-extracts; an unchanged file is free on a re-run;
  * editing a PARSER busts only what that parser produced;
  * editing triage thresholds / scoring does NOT bust the cache — you re-triage off
    the cache instantly (the expensive parse is reused).

Extraction runs WITH product-master enrichment (the normal pipeline), so a cached
result is byte-for-byte what triage_batch.py / build_product_synonyms.py /
regression_test.py would have produced themselves. That equivalence is the whole
point: the orchestrator can replace the per-script extraction without changing any
verdict. (The header-scan and relocate tools disable enrichment for speed, but
enrichment only touches `rows`, never `headers_detected`, so their results are
unaffected by reading an enriched cache.)
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from extractors import party_pdf, party_xlsx, stock_pdf, stock_xlsx  # noqa: E402

ROUTES = {
    "party_pdf": party_pdf.extract,
    "party_xlsx": party_xlsx.extract,
    "stock_pdf": stock_pdf.extract,
    "stock_xlsx": stock_xlsx.extract,
}

PDF_EXTS = {".pdf"}
XLSX_EXTS = {".xlsx", ".xls", ".xlsm"}

DEFAULT_CACHE_DIR = ROOT / "_extract_cache"

# If no file finishes within this many seconds, the still-pending worker(s) are
# treated as hung (e.g. a corrupt PDF stuck inside pdfplumber) and abandoned so the
# batch always finishes instead of hanging forever. Set generously: it is a
# whole-batch "nothing is making progress" stall detector, not a per-file budget, so
# it must comfortably exceed the slowest single legitimate extraction.
PER_FILE_TIMEOUT_S = 600.0

# Core modules that actually participate in extraction (imported by the pipelines).
# Triage/quality/scoring are deliberately excluded so tuning them does not force a
# full re-extract of the batch.
_EXTRACTION_CORE = ("canonical.py", "header_match.py", "line_ledger.py",
                    "pack_match.py", "product_master.py")
# Core modules that affect ONE route family only (so editing them busts just that
# family's cache, never the other). party_filter is imported solely by the party pipelines.
_ROUTE_ONLY_CORE = {"party": ("party_filter.py",)}


def report_type(route: str) -> str:
    return "stock" if route.startswith("stock") else "party"


def exts_for_route(route: str) -> set[str]:
    return PDF_EXTS if route.endswith("pdf") else XLSX_EXTS


# --------------------------------------------------------------------------- #
# cache signature & keys
# --------------------------------------------------------------------------- #
def extraction_code_sig() -> str:
    """Fingerprint only the source that changes extraction output."""
    h = hashlib.sha1()
    base = ROOT / "extractors"
    if base.exists():
        for p in sorted(base.rglob("*.py")):
            h.update(p.relative_to(ROOT).as_posix().encode())
            h.update(p.read_bytes())
    core = ROOT / "core"
    for name in _EXTRACTION_CORE:
        p = core / name
        if p.exists():
            h.update(name.encode())
            h.update(p.read_bytes())
    return h.hexdigest()[:16]


def _route_sources(route: str):
    """Source files whose content affects THIS route's extraction output:
    the shared core fields/matchers, any root-level extractor helper, and the
    route's own package. Editing one route therefore never busts another's cache."""
    ext = ROOT / "extractors"
    if ext.exists():
        yield from sorted(ext.glob("*.py"))            # root-level shared (e.g. __init__)
        rdir = ext / route
        if rdir.exists():
            yield from sorted(rdir.rglob("*.py"))       # this route's package only
    core = ROOT / "core"
    family = report_type(route)  # "party" | "stock"
    names = tuple(_EXTRACTION_CORE) + _ROUTE_ONLY_CORE.get(family, ())
    for name in names:
        p = core / name
        if p.exists():
            yield p


def route_code_sig(route: str) -> str:
    """Per-route fingerprint, so a change to one route only invalidates its cache."""
    h = hashlib.sha1()
    for p in _route_sources(route):
        h.update(p.relative_to(ROOT).as_posix().encode())
        h.update(p.read_bytes())
    return h.hexdigest()[:16]


def file_sha1(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def _entry_path(cache_dir: Path, route: str, sha1: str) -> Path:
    return cache_dir / route / f"{sha1}.json"


def _ensure_sig(cache_dir: Path, code_sig: str) -> None:
    """Wipe the cache if the extraction code changed (stale results)."""
    sig_file = cache_dir / "_code_sig.txt"
    cache_dir.mkdir(parents=True, exist_ok=True)
    if sig_file.exists() and sig_file.read_text(encoding="utf-8").strip() == code_sig:
        return
    # signature changed (or first run) -> drop any existing entries
    for route in ROUTES:
        d = cache_dir / route
        if d.exists():
            for f in d.glob("*.json"):
                try:
                    f.unlink()
                except OSError:
                    pass
    sig_file.write_text(code_sig, encoding="utf-8")


def _ensure_route_sig(cache_dir: Path, route: str, sig: str) -> None:
    """Wipe only THIS route's cache entries if the route's extraction code changed."""
    rdir = cache_dir / route
    sig_file = rdir / "_sig.txt"
    if sig_file.exists() and sig_file.read_text(encoding="utf-8").strip() == sig:
        return
    if rdir.exists():
        for f in rdir.glob("*.json"):
            try:
                f.unlink()
            except OSError:
                pass
    rdir.mkdir(parents=True, exist_ok=True)
    sig_file.write_text(sig, encoding="utf-8")


# --------------------------------------------------------------------------- #
# extraction worker (top-level so it is picklable for ProcessPoolExecutor)
# --------------------------------------------------------------------------- #
def extract_one(route: str, path_str: str) -> dict:
    """Extract a single file. A crash is captured (never kills the batch) so the
    downstream triage maps it to EXTRACTION_CRASHED exactly as triage_batch did."""
    path = Path(path_str)
    try:
        result = ROUTES[route](path.read_bytes(), {"filename": path.name}) or {}
        return result
    except Exception as exc:  # corrupt/locked/image-only file
        return {"_extract_error": f"{type(exc).__name__}: {exc}"}


def _worker(route: str, path_str: str) -> tuple[str, str, dict]:
    data = Path(path_str).read_bytes()
    sha1 = file_sha1(data)
    try:
        result = ROUTES[route](data, {"filename": Path(path_str).name}) or {}
    except Exception as exc:
        result = {"_extract_error": f"{type(exc).__name__}: {exc}"}
    return route, sha1, result


# --------------------------------------------------------------------------- #
# public API
# --------------------------------------------------------------------------- #
def extract_batch(jobs, cache_dir: Path | None = None, workers: int = 1,
                  refresh: bool = False, progress: bool = True,
                  per_file_timeout: float = PER_FILE_TIMEOUT_S) -> dict:
    """Extract every (route, Path) job once, using/refreshing the on-disk cache.

    Returns {str(path): result}. Cache hits cost only a read+hash; misses pay the
    extraction (parallelised across `workers` processes).
    """
    cache_dir = Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR
    jobs = [(route, Path(p)) for route, p in jobs]
    # Per-route invalidation: editing one route's extractor only re-extracts that
    # route, not the whole batch (a change to core/ shared files busts every route).
    for route in {r for r, _ in jobs}:
        _ensure_route_sig(cache_dir, route, route_code_sig(route))
    results: dict[str, dict] = {}
    misses = []  # (route, path, sha1)
    hits = 0
    for route, path in jobs:
        try:
            data = path.read_bytes()
        except OSError as exc:
            results[str(path)] = {"_extract_error": f"unreadable: {exc}"}
            continue
        sha1 = file_sha1(data)
        entry = _entry_path(cache_dir, route, sha1)
        if not refresh and entry.exists():
            try:
                results[str(path)] = json.loads(entry.read_text(encoding="utf-8"))
                hits += 1
                continue
            except Exception:
                pass  # corrupt cache entry -> re-extract
        misses.append((route, path, sha1))

    if progress and hits:
        print(f"  {hits} file(s) reused from extract cache, {len(misses)} to (re)extract")

    def _store(route: str, sha1: str, result: dict) -> None:
        entry = _entry_path(cache_dir, route, sha1)
        entry.parent.mkdir(parents=True, exist_ok=True)
        entry.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")

    if workers <= 1 or len(misses) <= 1:
        for n, (route, path, sha1) in enumerate(misses, 1):
            result = extract_one(route, str(path))
            _store(route, sha1, result)
            results[str(path)] = result
            if progress:
                tag = "ERR" if result.get("_extract_error") else "ok "
                print(f"  [{n}/{len(misses)}] {tag} {path.name}")
    else:
        from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
        try:
            ex = ProcessPoolExecutor(max_workers=workers)
        except (OSError, RuntimeError) as exc:
            # Windows spawn can fail in some shells; fall back to serial.
            if progress:
                print(f"  workers unavailable ({exc}); falling back to --workers 1")
            for n, (route, path, sha1) in enumerate(misses, 1):
                result = extract_one(route, str(path))
                _store(route, sha1, result)
                results[str(path)] = result
                if progress:
                    tag = "ERR" if result.get("_extract_error") else "ok "
                    print(f"  [{n}/{len(misses)}] {tag} {path.name}")
            return results

        try:
            futs = {ex.submit(_worker, route, str(path)): (route, path, sha1)
                    for route, path, sha1 in misses}
            pending = set(futs)
            done = 0
            while pending:
                finished, pending = wait(pending, timeout=per_file_timeout,
                                         return_when=FIRST_COMPLETED)
                if not finished:
                    # No file completed within per_file_timeout -> the still-running
                    # worker(s) are stuck (e.g. a corrupt PDF inside pdfplumber).
                    # Abandon every unfinished file so the batch finishes. A timeout is
                    # environmental, not a property of the file's bytes, so it is
                    # deliberately NOT written to the cache (that would poison a good
                    # file into a permanent error); the file is re-extracted next run.
                    # NOTE: this abandons all still-pending files together. The window
                    # resets on every completion, so this only fires when NOTHING
                    # finishes for per_file_timeout — the rare worst case being a tail
                    # of only large, legitimately-slow files, which simply retry.
                    if progress:
                        print(f"  no progress for {per_file_timeout:.0f}s; abandoning "
                              f"{len(pending)} unfinished file(s):")
                    for fut in pending:
                        route, path, sha1 = futs[fut]
                        results[str(path)] = {"_extract_error": f"timeout after {per_file_timeout:.0f}s"}
                        done += 1
                        if progress:
                            print(f"  [{done}/{len(misses)}] TIMEOUT {path.name}")
                    # A worker already executing a hung task cannot be cancelled, so
                    # terminate the worker processes: a stuck one would otherwise keep
                    # burning CPU and block interpreter exit (the pool's atexit join
                    # waits on it forever). We do NOT fut.cancel() first — terminating
                    # makes the pool set BrokenProcessPool on the pending futures, and
                    # cancelling them beforehand would make that raise InvalidStateError
                    # in the pool's manager thread. We never read these futures again.
                    for proc in list(getattr(ex, "_processes", {}).values()):
                        if proc.is_alive():
                            proc.terminate()
                    break
                for fut in finished:
                    route, path, sha1 = futs[fut]
                    try:
                        _, _, result = fut.result()
                    except Exception as exc:  # worker process died
                        result = {"_extract_error": f"{type(exc).__name__}: {exc}"}
                    _store(route, sha1, result)
                    results[str(path)] = result
                    done += 1
                    if progress:
                        tag = "ERR" if result.get("_extract_error") else "ok "
                        print(f"  [{done}/{len(misses)}] {tag} {path.name}")
        finally:
            # Return immediately without joining a hung worker. We avoid
            # cancel_futures here: on the timeout path the workers were terminated,
            # which makes the pool fail the pending futures itself, and concurrently
            # cancelling them would race that into an InvalidStateError.
            ex.shutdown(wait=False)
    return results


def get(route: str, path, cache_dir: Path | None = None, refresh: bool = False) -> dict:
    """Single-file cache-aware extraction (used by ad-hoc callers)."""
    out = extract_batch([(route, Path(path))], cache_dir=cache_dir,
                         workers=1, refresh=refresh, progress=False)
    return next(iter(out.values()))


if __name__ == "__main__":
    # tiny smoke test: extract one file twice, prove the 2nd is a cache hit
    import argparse
    ap = argparse.ArgumentParser(description="Shared extraction cache (smoke test)")
    ap.add_argument("--route", required=True, choices=sorted(ROUTES))
    ap.add_argument("--file", required=True)
    args = ap.parse_args()
    t0 = time.time()
    r1 = get(args.route, args.file, refresh=True)
    t1 = time.time()
    r2 = get(args.route, args.file)
    t2 = time.time()
    print(f"cold {t1 - t0:.2f}s  warm {t2 - t1:.3f}s")
    print(f"rows={len(r1.get('rows') or [])} layout={(r1.get('debug') or {}).get('layout')}")
    print(f"identical={json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True)}")
