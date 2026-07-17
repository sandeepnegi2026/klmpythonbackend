#!/usr/bin/env python3
"""
render_dashboard_simple.py — render a batch _triage/<batch> directory into a clean,
self-contained ``dashboard.html`` in the SIMPLE reference format:

  - <h1> "<batch> — extraction batch dashboard"
  - a headline "head" card + a "By route" summary table
    (Route | Total | GREEN | AMBER | RED | ERROR)
  - an "All files (N)" table
    (File (relative path) | Route | Status | Problem | Reason | Rows | Layout)
  - a tiny client-side filter (search box + status/route selects)

Source of truth for BOTH tables is ``_files.json`` (a JSON list of objects, each with
keys: file, route, status, problem, reason, rows, layout). The By-route summary is
computed by grouping _files.json by route x status; the All-files table is every row.
``run.json`` is read only for the headline ``.sub`` line (route count / total files).

This is DELIBERATELY separate from scripts/render_dashboard.py (the richer
"DO THIS NEXT" format used by run_batch.py). Running a batch will overwrite
dashboard.html back to that format; re-run this script to restore the simple one.

Usage:
    python scripts/render_dashboard_simple.py "_triage/15 July"
    python scripts/render_dashboard_simple.py --batch "15 July"
"""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Status order + tag colors — copied VERBATIM from the reference dashboard.html
STATUSES = ["GREEN", "AMBER", "RED", "ERROR"]
TAG_COLOR = {
    "GREEN": ("#e7f6ee", "#16794c"),
    "AMBER": ("#fdf5e6", "#9a6700"),
    "RED":   ("#fdeceb", "#b42318"),
    "ERROR": ("#f1f2f4", "#6b7280"),
}
# Pill (headline) colors — same background/foreground pairs as the reference.
PILL_COLOR = dict(TAG_COLOR)
# Per-status text color used in the By-route numeric cells (reference: the tag fg).
COL_COLOR = {k: v[1] for k, v in TAG_COLOR.items()}

# The <style> block, copied BYTE-FOR-BYTE from the reference dashboard.html.
STYLE = """<style>
body{font:14px system-ui,Segoe UI,Arial;margin:0;background:#f6f7f9;color:#1f2329}
.wrap{max-width:1280px;margin:0 auto;padding:24px}
h1{font-size:22px;margin:0 0 2px}.sub{color:#6b7280;margin:0 0 18px}
.head{background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:18px 20px;margin-bottom:18px;box-shadow:0 1px 2px rgba(0,0,0,.04)}
.bigrow{display:flex;gap:26px;flex-wrap:wrap;align-items:baseline}
.big{font-size:30px;font-weight:700}
.pill{display:inline-block;padding:3px 10px;border-radius:11px;font-weight:600;margin-right:6px}
h2{font-size:16px;margin:22px 0 8px}
table{border-collapse:collapse;width:100%;background:#fff;border:1px solid #e5e7eb;border-radius:10px;overflow:hidden}
th,td{border-bottom:1px solid #eef0f2;padding:7px 10px;text-align:left;vertical-align:top}
th{background:#f3f4f6;font-weight:600;position:sticky;top:0;cursor:pointer}
tr:last-child td{border-bottom:none}
.tag{display:inline-block;padding:1px 8px;border-radius:9px;font-size:12px;font-weight:600}
.rc{color:#9aa0a6;font-size:12px;font-family:ui-monospace,Consolas,monospace}
.mono{font-family:ui-monospace,Consolas,monospace;font-size:12px}
.controls{margin:8px 0}.controls input,.controls select{font:13px system-ui;padding:6px 8px;border:1px solid #d1d5db;border-radius:8px}
tr.hide{display:none}
</style>"""

SCRIPT = """<script>
function applyFilter(){
 var q=document.getElementById('q').value.toLowerCase();
 var s=document.getElementById('st').value;
 var rt=document.getElementById('rt').value;
 document.querySelectorAll('tbody tr').forEach(function(tr){
  var okS=!s||tr.dataset.status===s;
  var okR=!rt||tr.dataset.route===rt;
  var okQ=!q||tr.textContent.toLowerCase().indexOf(q)>=0;
  tr.classList.toggle('hide',!(okS&&okR&&okQ));
 });
}
</script>"""


def _esc(v) -> str:
    return html.escape("" if v is None else str(v))


def _pct(n: int, d: int) -> float:
    return round(100 * n / d, 1) if d else 0.0


def _load(triage_dir: Path):
    files = json.loads((triage_dir / "_files.json").read_text(encoding="utf-8"))
    run_path = triage_dir / "run.json"
    run = json.loads(run_path.read_text(encoding="utf-8")) if run_path.exists() else {}
    if not isinstance(files, list):
        raise SystemExit(f"_files.json must be a JSON list, got {type(files).__name__}")
    return files, run


def render_html(files: list[dict], run: dict, batch: str) -> str:
    total = len(files)

    # --- headline counts + By-route matrix, grouped from _files.json -------- #
    status_totals = {s: 0 for s in STATUSES}
    routes: dict[str, dict[str, int]] = {}
    for o in files:
        st = o.get("status") or ""
        rt = o.get("route") or ""
        if st not in status_totals:            # tolerate any unexpected status
            status_totals[st] = 0
        status_totals[st] += 1
        row = routes.setdefault(rt, {s: 0 for s in STATUSES})
        row.setdefault(st, 0)
        row[st] += 1

    # --- head card ---------------------------------------------------------- #
    green = status_totals.get("GREEN", 0)
    pills = []
    for s in STATUSES:
        n = status_totals.get(s, 0)
        bg, fg = PILL_COLOR[s]
        pills.append(
            f"<span class='pill' style='background:{bg};color:{fg}'>"
            f"{s} {n} · {_pct(n, total)}%</span>"
        )
    big_fg = TAG_COLOR["GREEN"][1]

    n_routes = len(run.get("route_split", routes)) or len(routes)
    sub = f"{total} files across {n_routes} routes · per-file status after batch-2 parser integration"

    out = []
    out.append("<!doctype html><meta charset='utf-8'>"
               f"<title>Batch dashboard — {_esc(batch)}</title>")
    out.append(STYLE)
    out.append("")
    out.append("<div class='wrap'>")
    out.append(f"<h1>{_esc(batch)} — extraction batch dashboard</h1>")
    out.append(f"<p class='sub'>{_esc(sub)}</p>")
    out.append("<div class='head'>")
    out.append(f" <div class='bigrow'><div class='big' style='color:{big_fg}'>{green} GREEN</div>")
    out.append(f" <div>{' '.join(pills)}</div></div>")
    out.append("</div>")

    # --- By route table ----------------------------------------------------- #
    out.append("<h2>By route</h2>")
    out.append("<table><thead><tr><th>Route</th><th>Total</th><th>GREEN</th>"
               "<th>AMBER</th><th>RED</th><th>ERROR</th></tr></thead>")
    out.append("<tbody>")
    rowbits = []
    for rt in sorted(routes):
        r = routes[rt]
        rtot = sum(r.get(s, 0) for s in r)
        cells = [f"<td class='mono'>{_esc(rt)}</td>", f"<td>{rtot}</td>"]
        for s in STATUSES:
            cells.append(f"<td style='color:{COL_COLOR[s]}'>{r.get(s, 0)}</td>")
        rowbits.append("<tr>" + "".join(cells) + "</tr>")
    out.append("".join(rowbits))
    out.append("</tbody></table>")

    # --- All files table ---------------------------------------------------- #
    out.append(f"<h2>All files ({total})</h2>")
    out.append("<div class='controls'>")
    out.append(" <input id='q' placeholder='search file / reason / layout…' "
               "oninput='applyFilter()' size='34'>")
    st_opts = "".join(f"<option>{s}</option>" for s in STATUSES)
    out.append(f" <select id='st' onchange='applyFilter()'><option value=''>all status</option>{st_opts}</select>")
    rt_opts = "".join(f"<option>{_esc(rt)}</option>" for rt in sorted(routes))
    out.append(f" <select id='rt' onchange='applyFilter()'><option value=''>all routes</option>{rt_opts}</select>")
    out.append("</div>")
    out.append("<table><thead><tr><th>File (relative path)</th><th>Route</th>"
               "<th>Status</th><th>Problem</th><th>Reason</th><th>Rows</th>"
               "<th>Layout</th></tr></thead>")
    out.append("<tbody>")

    body = []
    for o in files:
        st = o.get("status") or ""
        rt = o.get("route") or ""
        bg, fg = TAG_COLOR.get(st, ("#f1f2f4", "#6b7280"))
        tag = f"<span class='tag' style='background:{bg};color:{fg}'>{_esc(st)}</span>"
        body.append(
            f"<tr data-status='{_esc(st)}' data-route='{_esc(rt)}'>"
            f"<td class='mono'>{_esc(o.get('file'))}</td>"
            f"<td class='mono'>{_esc(rt)}</td>"
            f"<td>{tag}</td>"
            f"<td>{_esc(o.get('problem'))}</td>"
            f"<td class='rc'>{_esc(o.get('reason'))}</td>"
            f"<td>{_esc(o.get('rows'))}</td>"
            f"<td class='mono' style='color:#6b7280'>{_esc(o.get('layout'))}</td>"
            "</tr>"
        )
    out.append("".join(body))
    out.append("</tbody></table>")
    out.append("</div>")
    out.append(SCRIPT)
    return "\n".join(out) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("triage_dir", nargs="?",
                    help="path to _triage/<batch> directory")
    ap.add_argument("--batch", help="batch name (resolves to _triage/<batch>)")
    args = ap.parse_args()

    if args.triage_dir:
        triage_dir = Path(args.triage_dir)
    elif args.batch:
        triage_dir = ROOT / "_triage" / args.batch
    else:
        ap.error("provide a triage dir or --batch")

    if not triage_dir.is_absolute():
        triage_dir = (ROOT / triage_dir).resolve()
    if not triage_dir.exists():
        raise SystemExit(f"triage dir not found: {triage_dir}")

    batch = args.batch or triage_dir.name
    files, run = _load(triage_dir)
    batch = run.get("batch", batch)

    html_text = render_html(files, run, batch)
    out_path = triage_dir / "dashboard.html"
    out_path.write_text(html_text, encoding="utf-8")

    # ---- console verification --------------------------------------------- #
    from collections import Counter
    sc = Counter(o.get("status") for o in files)
    print(f"wrote {out_path}")
    print(f"all-files rows: {len(files)}")
    print("by-route status sums (from _files.json):",
          {s: sc.get(s, 0) for s in STATUSES})
    if run.get("buckets"):
        print("run.json buckets              :", run["buckets"])


if __name__ == "__main__":
    main()
