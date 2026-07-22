"""Corpus shadow run for the line-accounting ledger — the row-loss league table.

Extracts (or reads from the shared cache) every Final_Data file, collects each
file's ``line_audit`` + ``total_reconcile``, simulates the UNACCOUNTED_LINES
gate (thresholds from core/triage.THRESHOLDS, no verdicts touched), and
aggregates per (route, layout):

    files, would_fire, unexplained lines, % of data lines, totals-found rate,
    worst sample lines with their file paths.

Output: _audit/ledger_league/ledger_league.json + LEDGER_LEAGUE.md — the
prioritized burn-down worklist. Each cluster is then classified by a human/dev:
(a) ledger-taxonomy bug -> fix core/line_ledger.py rules,
(b) real parser drop    -> fix that layout (regression-gated),
(c) legitimately unparseable -> document.

Usage:
    python scripts/ledger_league.py [--root ../../Final_Data] [--workers 10]
"""
import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import batch_extract  # noqa: E402
from scripts.batch_extract import ROUTES, exts_for_route  # noqa: E402
from core.triage import THRESHOLDS  # noqa: E402
from core.quality import build_quality  # noqa: E402
from scripts.batch_extract import report_type  # noqa: E402

OUT_DIR = ROOT / "_audit" / "ledger_league"


def would_fire(la, tr=None):
    """Mirror the real triage gate: ledger thresholds AND the printed-total
    suppression (a file whose extracted sums match the vendor's own grand total
    is proven complete, so unexplained lines never fire)."""
    if tr and tr.get("found") and tr.get("ok"):
        return False
    c = (la or {}).get("counts") or {}
    return bool(
        (la or {}).get("applicable")
        and c.get("data", 0) >= THRESHOLDS["unaccounted_min_data"]
        and c.get("unexplained", 0) >= THRESHOLDS["unaccounted_min_lines"]
        and ((la or {}).get("unexplained_ratio") or 0.0) >= THRESHOLDS["unaccounted_ratio"]
    )


def discover(root: Path):
    """(route, path) for every file under the Final_Data-style tree, using the
    same folder conventions as run_batch (Party report / Stock report...)."""
    jobs = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = str(p.relative_to(root)).lower()
        if any(seg in rel for seg in ("_wrong_format", "_misfiled", "need-review", "need review")):
            continue
        is_party = "party" in rel
        is_stock = "stock" in rel
        if not (is_party or is_stock):
            continue
        route_base = "party" if is_party else "stock"
        ext = p.suffix.lower()
        if ext == ".pdf":
            route = f"{route_base}_pdf"
        elif ext in (".xlsx", ".xls", ".xlsm"):
            route = f"{route_base}_xlsx"
        else:
            continue
        if ext in exts_for_route(route):
            jobs.append((route, str(p)))
    return jobs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(ROOT.parent.parent / "Final_Data"))
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--limit", type=int, default=0, help="debug: only first N files")
    args = ap.parse_args()

    root = Path(args.root)
    jobs = discover(root)
    if args.limit:
        jobs = jobs[: args.limit]
    print(f"corpus: {len(jobs)} files under {root}")

    by_route = defaultdict(list)
    for route, path in jobs:
        by_route[route].append(path)

    rows_out = []
    for route, paths in sorted(by_route.items()):
        print(f"[{route}] {len(paths)} files ...")
        results = batch_extract.extract_batch(
            [(route, p) for p in paths], workers=args.workers
        )
        for path in paths:
            # extract_batch keys results by str(Path(path)), not (route, path).
            res = results.get(str(Path(path))) or {}
            la = res.get("line_audit") or {}
            layout = ((res.get("debug") or {}).get("layout")
                      or (res.get("debug") or {}).get("detected_format") or "?")
            try:
                q = build_quality(res, report_type(route))
                tr = (q.get("checks") or {}).get("total_reconcile") or {}
                bucket = (q.get("triage") or {}).get("bucket")
            except Exception as exc:  # noqa: BLE001
                tr, bucket = {}, f"ERR:{exc}"
            c = la.get("counts") or {}
            rows_out.append({
                "route": route,
                "layout": layout,
                "file": path,
                "bucket": bucket,
                "rows": len(res.get("rows") or []),
                "applicable": bool(la.get("applicable")),
                "data": c.get("data", 0),
                "unexplained": c.get("unexplained", 0),
                "ratio": la.get("unexplained_ratio") or 0.0,
                "would_fire": would_fire(la, tr),
                "elapsed_ms": la.get("elapsed_ms"),
                "total_found": bool(tr.get("found")),
                "total_ok": tr.get("ok"),
                "total_source": tr.get("source"),
                "sample": (la.get("unexplained_sample") or [])[:3],
            })

    # aggregate
    agg = defaultdict(lambda: {"files": 0, "fire": 0, "unexplained": 0, "data": 0,
                               "green_fire": 0, "total_found": 0, "samples": []})
    for r in rows_out:
        k = (r["route"], r["layout"])
        a = agg[k]
        a["files"] += 1
        a["data"] += r["data"]
        a["unexplained"] += r["unexplained"]
        a["total_found"] += 1 if r["total_found"] else 0
        if r["would_fire"]:
            a["fire"] += 1
            if r["bucket"] == "GREEN":
                a["green_fire"] += 1
            if len(a["samples"]) < 5 and r["sample"]:
                a["samples"].append({"file": Path(r["file"]).name, "lines": r["sample"]})

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "ledger_rows.json").write_text(
        json.dumps(rows_out, indent=1, ensure_ascii=False), encoding="utf-8")

    league = sorted(
        ({"route": k[0], "layout": k[1], **v,
          "pct": round(100.0 * v["unexplained"] / v["data"], 2) if v["data"] else 0.0,
          "total_found_rate": round(v["total_found"] / v["files"], 2)}
         for k, v in agg.items()),
        key=lambda x: (-x["fire"], -x["unexplained"]))
    (OUT_DIR / "ledger_league.json").write_text(
        json.dumps(league, indent=1, ensure_ascii=False), encoding="utf-8")

    lines = ["# Ledger league — unexplained source lines per (route, layout)", "",
             f"files={len(rows_out)}  would_fire={sum(1 for r in rows_out if r['would_fire'])}  "
             f"(GREEN files that would fire: {sum(a['green_fire'] for a in agg.values())})", "",
             "| route | layout | files | would_fire | GREEN-fire | unexplained | % of data | totals-found |",
             "|---|---|---|---|---|---|---|---|"]
    for e in league:
        if not e["fire"] and not e["unexplained"]:
            continue
        lines.append(f"| {e['route']} | {e['layout']} | {e['files']} | {e['fire']} | "
                     f"{e['green_fire']} | {e['unexplained']} | {e['pct']} | {e['total_found_rate']} |")
    lines.append("")
    for e in league[:15]:
        if not e["samples"]:
            continue
        lines.append(f"## {e['route']} / {e['layout']}")
        for s in e["samples"]:
            lines.append(f"- **{s['file']}**")
            for ln in s["lines"]:
                lines.append(f"    - `{ln[:110]}`")
        lines.append("")
    (OUT_DIR / "LEDGER_LEAGUE.md").write_text("\n".join(lines), encoding="utf-8")

    fired = sum(1 for r in rows_out if r["would_fire"])
    green_total = sum(1 for r in rows_out if r["bucket"] == "GREEN")
    green_fired = sum(1 for r in rows_out if r["would_fire"] and r["bucket"] == "GREEN")
    print(f"\nfiles={len(rows_out)}  would_fire={fired}  "
          f"GREEN={green_total}  GREEN-would-fire={green_fired} "
          f"({round(100.0 * green_fired / green_total, 2) if green_total else 0}% of GREEN)")
    print(f"league -> {OUT_DIR / 'LEDGER_LEAGUE.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
