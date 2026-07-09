"""Generate per_file_report.md + dashboard.html for a triage run, matching the
_triage/Excel/ report style. Reads the latest triage_report_*.csv in a dir.
Usage: python scratch/make_report.py <triage_out_dir> "<Report Title>"
"""
import sys, csv, glob, html, os
from pathlib import Path

out_dir = Path(sys.argv[1])
title = sys.argv[2] if len(sys.argv) > 2 else out_dir.name

csvs = sorted(glob.glob(str(out_dir / "triage_report_*.csv")))
if not csvs:
    print("no triage_report_*.csv in", out_dir); sys.exit(1)
rows = list(csv.DictReader(open(csvs[-1], encoding="utf-8")))
print("read", len(rows), "rows from", os.path.basename(csvs[-1]))

ORDER = {"GREEN": 0, "AMBER": 1, "RED": 2, "ERROR": 3}
BCOLOR = {"GREEN": "#d7f5dd", "AMBER": "#fff3cd", "RED": "#f8d7da", "ERROR": "#e2e3e5"}
def bkt(r): return r.get("bucket", "ERROR")
counts = {b: sum(1 for r in rows if bkt(r) == b) for b in ("GREEN", "AMBER", "RED", "ERROR")}
N = len(rows)

def sanity(r):
    v = r.get("sanity_eff", "")
    return v if v not in (None, "") else ""
def note(r):
    return "OK" if bkt(r) == "GREEN" else (r.get("reason_code") or r.get("reason") or "")

# ---------- per_file_report.md ----------
md = []
md.append(f"# Per-file extraction report — {title}  ({N} files)\n")
md.append(f"GREEN {counts['GREEN']}  ·  AMBER {counts['AMBER']}  ·  RED {counts['RED']}"
          + (f"  ·  ERROR {counts['ERROR']}" if counts['ERROR'] else "") + "\n")
for b in ("GREEN", "AMBER", "RED", "ERROR"):
    grp = sorted([r for r in rows if bkt(r) == b], key=lambda r: (r.get("layout", ""), r.get("file_name", "")))
    if not grp:
        continue
    md.append(f"\n## {b} ({len(grp)})\n")
    md.append("| layout | rows | sanity | file | note |")
    md.append("|---|---|---|---|---|")
    for r in grp:
        md.append(f"| {r.get('layout','')} | {r.get('row_count','')} | {sanity(r)} | {r.get('file_name','')} | {note(r)} |")
(out_dir / "per_file_report.md").write_text("\n".join(md) + "\n", encoding="utf-8")

# ---------- per_file_report.csv (compact, Excel-style columns) ----------
with (out_dir / "per_file_report.csv").open("w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh)
    w.writerow(["bucket", "code", "layout", "rows", "eff", "vendor", "file", "reason"])
    for r in sorted(rows, key=lambda r: (ORDER.get(bkt(r), 9), r.get("layout", ""))):
        w.writerow([bkt(r), r.get("reason_code", ""), r.get("layout", ""), r.get("row_count", ""),
                    sanity(r), r.get("vendor", ""), r.get("file_name", ""), r.get("reason", "")])

# ---------- clusters (RED+AMBER by layout) ----------
clusters = {}
for r in rows:
    if bkt(r) in ("AMBER", "RED", "ERROR"):
        k = (r.get("layout", "?"), r.get("reason_code", "?"))
        c = clusters.setdefault(k, {"n": 0, "ex": r.get("file_name", "")})
        c["n"] += 1
cl_sorted = sorted(clusters.items(), key=lambda kv: -kv[1]["n"])

# ---------- dashboard.html ----------
def esc(v): return html.escape("" if v is None else str(v))
def pct(n): return round(100 * n / N) if N else 0
H = []
H.append("<!doctype html><meta charset='utf-8'><title>" + esc(title) + " — dashboard</title>")
H.append("""<style>
body{font:14px/1.5 -apple-system,Segoe UI,Arial,sans-serif;margin:24px;color:#222}
h1{margin:0 0 4px} .sub{color:#666;margin-bottom:16px}
.pills span{display:inline-block;padding:6px 12px;border-radius:14px;margin-right:8px;font-weight:600}
table{border-collapse:collapse;width:100%;margin:12px 0}
th,td{border:1px solid #ddd;padding:5px 8px;text-align:left;font-size:13px}
th{background:#f4f4f4;position:sticky;top:0}
td.num{text-align:right}
.bar{height:22px;border-radius:4px;overflow:hidden;display:flex;margin:10px 0 18px;max-width:640px}
.bar>i{display:block;height:100%}
h2{margin-top:26px;border-bottom:2px solid #eee;padding-bottom:4px}
</style>""")
H.append(f"<h1>{esc(title)}</h1><div class='sub'>{N} files · GREEN {counts['GREEN']} ({pct(counts['GREEN'])}%) · AMBER {counts['AMBER']} · RED {counts['RED']}"
         + (f" · ERROR {counts['ERROR']}" if counts['ERROR'] else "") + "</div>")
H.append("<div class='bar'>"
         + f"<i style='background:#28a745;width:{pct(counts['GREEN'])}%'></i>"
         + f"<i style='background:#ffc107;width:{pct(counts['AMBER'])}%'></i>"
         + f"<i style='background:#dc3545;width:{pct(counts['RED'])}%'></i></div>")
H.append("<div class='pills'>"
         + "".join(f"<span style='background:{BCOLOR[b]}'>{b}: {counts[b]}</span>" for b in ("GREEN","AMBER","RED","ERROR") if counts[b] or b!="ERROR")
         + "</div>")

if cl_sorted:
    H.append("<h2>Work-list — clusters needing attention (by layout)</h2>")
    H.append("<table><tr><th>#</th><th>layout</th><th>reason</th><th class='num'>files</th><th>example</th></tr>")
    for i,((lay,rc),c) in enumerate(cl_sorted,1):
        H.append(f"<tr><td class='num'>{i}</td><td>{esc(lay)}</td><td>{esc(rc)}</td><td class='num'>{c['n']}</td><td>{esc(c['ex'])}</td></tr>")
    H.append("</table>")

H.append("<h2>All files</h2>")
H.append("<table><tr><th>bucket</th><th>layout</th><th class='num'>rows</th><th class='num'>sanity</th><th>file</th><th>note</th></tr>")
for r in sorted(rows, key=lambda r:(ORDER.get(bkt(r),9), r.get("layout",""), r.get("file_name",""))):
    b=bkt(r)
    H.append(f"<tr style='background:{BCOLOR.get(b,'#fff')}'><td>{b}</td><td>{esc(r.get('layout',''))}</td>"
             f"<td class='num'>{esc(r.get('row_count',''))}</td><td class='num'>{esc(sanity(r))}</td>"
             f"<td>{esc(r.get('file_name',''))}</td><td>{esc(note(r))}</td></tr>")
H.append("</table>")
(out_dir / "dashboard.html").write_text("".join(H), encoding="utf-8")

print("wrote:", out_dir / "per_file_report.md")
print("wrote:", out_dir / "per_file_report.csv")
print("wrote:", out_dir / "dashboard.html")
print(f"GREEN {counts['GREEN']} · AMBER {counts['AMBER']} · RED {counts['RED']} · ERROR {counts['ERROR']}")
