#!/usr/bin/env python3
"""
render_dashboard.py — turn a run_batch record into ONE consolidated, self-contained
dashboard.html (open in a browser, no server) + a short SUMMARY.md digest.

This replaces the 8-12 scattered CSV/HTML/xlsx/txt artifacts a full run used to drop
across three folders. Plain-English problems are the DEFAULT; the terse reason-code
is secondary. The headline + "DO THIS NEXT" list tell a non-technical owner exactly
where to start and who handles each cluster.
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import batch_core as bc

BUCKET_COLOR = {"GREEN": "#d7f5dd", "AMBER": "#fff3cd", "RED": "#f8d7da", "ERROR": "#e2e3e5"}
WHO_COLOR = {"Dev": "#cfe2ff", "You decide": "#fff3cd", "Dev + you": "#e2d9f3",
             "OCR track": "#e2e3e5", "—": "#f0f0f0"}

# The user-facing triage verdict is 4 colours, not 3: the AMBER bucket splits on
# core/triage.py's `extraction_ok` (True = extraction proven correct but the vendor's
# own numbers don't balance; None = unconfirmed, a human should glance). GREEN/AMBER/RED
# stays the canonical gate enum (tests, relocate RED-gate); this badge is the display layer.
# key -> (label, colour). Order here is the display order (best -> worst).
BADGE = [
    ("correct",        "Correct",                        "#d7f5dd"),  # GREEN
    ("vendor_mismatch","Correct — vendor data mismatch", "#ffe0b2"),  # AMBER + extraction_ok True
    ("check",          "Needs a quick check",            "#fff3cd"),  # AMBER + extraction_ok None
    ("not_correct",    "Not correct",                    "#f8d7da"),  # RED
    ("crashed",        "Extraction crashed",             "#e2e3e5"),  # ERROR
]
BADGE_LABEL = {k: lbl for k, lbl, _ in BADGE}
BADGE_COLOR = {k: col for k, _, col in BADGE}


def _badge_of(row: dict) -> str:
    """Map a triage row -> one of the 4 (+ERROR) verdict badges. `extraction_ok` may be
    absent on older/run.json records — fall back to the bucket so it degrades to 3 states."""
    bucket = row.get("bucket")
    if bucket == "GREEN":
        return "correct"
    if bucket == "RED":
        return "not_correct"
    if bucket == "ERROR":
        return "crashed"
    if bucket == "AMBER":
        return "vendor_mismatch" if row.get("extraction_ok") is True else "check"
    return "check"


def _badge_counts(rows) -> dict:
    counts = {k: 0 for k, _, _ in BADGE}
    for r in rows or []:
        counts[_badge_of(r)] += 1
    return counts


def _esc(v):
    return html.escape("" if v is None else str(v))


def _pct(n, d):
    return round(100 * n / d) if d else 0


def _rel(path, name):
    """`stockist/slot/file` locator from a full path — the bare basename is ambiguous
    across 576 stockist folders that each contain a `KLM.pdf`."""
    if not path:
        return name or ""
    parts = str(path).replace("\\", "/").rstrip("/").split("/")
    return "/".join(parts[-3:]) if len(parts) >= 3 else "/".join(parts)


def _file_link(path, name):
    """Clickable file:// link labelled with the stockist/slot/file locator. The href is
    URL-encoded (spaces -> %20) so paths like 'SRI NAGENDRA DRUG AGENCIES/...' open."""
    rel = _rel(path, name)
    if not path:
        return _esc(rel)
    from urllib.parse import quote
    href = "file:///" + quote(str(path).replace("\\", "/"), safe="/:")
    return f"<a href='{href}' title='{_esc(path)}'>{_esc(rel)}</a>"


# --------------------------------------------------------------------------- #
# SUMMARY.md — ~15 line text digest (read by the agent / pasteable)
# --------------------------------------------------------------------------- #
def render_summary(rec: dict) -> str:
    b = rec.get("buckets", {})
    total = rec.get("total_files", 0)
    L = []
    L.append(f"# Batch summary — {rec.get('batch')}  ({rec.get('generated')})")
    L.append("")
    L.append(f"- Files: **{total}**  ·  GREEN {b.get('GREEN',0)} ({_pct(b.get('GREEN',0),total)}%) ·  "
             f"AMBER {b.get('AMBER',0)} ·  RED {b.get('RED',0)} ·  ERROR {b.get('ERROR',0)}")
    bc4 = _badge_counts(rec.get("triage_rows", []))
    if any(bc4.values()):
        L.append(f"- Triage badge (4-state) · **Correct {bc4['correct']}** ({_pct(bc4['correct'],total)}%) ·  "
                 f"Correct—vendor data mismatch {bc4['vendor_mismatch']} ·  "
                 f"Needs a quick check {bc4['check']} ·  Not correct {bc4['not_correct']} ·  "
                 f"Crashed {bc4['crashed']}")
    clusters = rec.get("clusters", [])
    L.append(f"- {len(clusters)} clusters need work · fixing the top {rec.get('est_green_gain_clusters',0)} "
             f"code-fixable clusters could clear ~{rec.get('est_green_gain',0)} files")
    L.append("")
    L.append("## DO THIS NEXT (top clusters by leverage)")
    for i, g in enumerate(clusters[:6], 1):
        L.append(f"{i}. {g['plain']} — **{g['fix_type']}** ({g['who']}) · {g['count']} files · "
                 f"`{g['route']}/{g['layout']}` · e.g. {g['example']}")
    if not clusters:
        L.append("- Nothing flagged — all files GREEN. 🎉")
    L.append("")
    L.append("## Needs your decision")
    p = rec.get("products", {})
    uh = rec.get("unmapped_headers", {})
    nuh = len(uh.get("party", [])) + len(uh.get("stock", []))
    L.append(f"- Misfiled files to move: {len(rec.get('misfiled', []))}  (apply: --apply-relocate)")
    L.append(f"- Unmapped header candidates: {nuh}  (editorial — add to canonical.py per Step 2)")
    L.append(f"- Product synonym candidates: {p.get('synonym_candidates',0)} across {p.get('products_touched',0)} "
             f"products; {p.get('unmatched',0)} new-product candidates  (apply: --apply-products)")
    L.append(f"- Scanned/corrupt to quarantine: {len(rec.get('quarantine', []))}  (apply: --apply-quarantine)")
    reg = rec.get("regression", [])
    rp = sum(r["passed"] for r in reg)
    rf = sum(r["failed"] for r in reg)
    L.append(f"- Regression: {rp} pass / {rf} fail across {len(reg)} curated suite(s)")
    mirror = rec.get("mirror", {})
    L.append(f"- Engine mirror: {'IN SYNC' if all(mirror.values()) else 'DRIFT — reconcile before deploy'}")
    L.append("")
    L.append(f"Full dashboard: dashboard.html (in this folder)")
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------- #
# dashboard.html
# --------------------------------------------------------------------------- #
_CSS = """
body{font:14px system-ui,Segoe UI,Arial;margin:0;background:#f6f7f9;color:#1f2329}
.wrap{max-width:1180px;margin:0 auto;padding:24px}
h1{font-size:22px;margin:0 0 2px}.sub{color:#6b7280;margin:0 0 18px}
.head{background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:18px 20px;margin-bottom:18px;
  box-shadow:0 1px 2px rgba(0,0,0,.04)}
.bigrow{display:flex;gap:26px;flex-wrap:wrap;align-items:baseline}
.big{font-size:30px;font-weight:700}
.pill{display:inline-block;padding:3px 10px;border-radius:11px;font-weight:600;margin-right:6px}
.note{margin-top:8px;color:#374151}
h2{font-size:16px;margin:24px 0 8px}
table{border-collapse:collapse;width:100%;background:#fff;border:1px solid #e5e7eb;border-radius:10px;overflow:hidden}
th,td{border-bottom:1px solid #eef0f2;padding:8px 10px;text-align:left;vertical-align:top}
th{background:#f3f4f6;font-weight:600;position:sticky;top:0}
tr:last-child td{border-bottom:none}
.tag{display:inline-block;padding:1px 8px;border-radius:9px;font-size:12px;font-weight:600}
.rc{color:#9aa0a6;font-size:12px}
details{background:#fff;border:1px solid #e5e7eb;border-radius:10px;margin:10px 0;padding:6px 14px}
summary{cursor:pointer;font-weight:600;padding:8px 0}
.muted{color:#6b7280}.mono{font-family:ui-monospace,Consolas,monospace;font-size:12px}
.gate{background:#fff7ed;border:1px solid #fed7aa;border-radius:10px;padding:12px 16px;margin:6px 0}
.ok{color:#16794c;font-weight:600}.bad{color:#b42318;font-weight:600}
"""


def _headline(rec):
    b = rec.get("buckets", {})
    total = rec.get("total_files", 0)
    pills = " ".join(
        f"<span class='pill' style='background:{BUCKET_COLOR[k]}'>{k} {b.get(k,0)} ({_pct(b.get(k,0),total)}%)</span>"
        for k in ("GREEN", "AMBER", "RED", "ERROR") if b.get(k))
    bc4 = _badge_counts(rec.get("triage_rows", []))
    badge_pills = " ".join(
        f"<span class='pill' style='background:{BADGE_COLOR[k]}'>{_esc(BADGE_LABEL[k])} {bc4[k]} ({_pct(bc4[k],total)}%)</span>"
        for k, _, _ in BADGE if bc4.get(k))
    badge_row = (f"<div class='note'><span class='muted'>Triage verdict (4-state):</span> {badge_pills}</div>"
                 if any(bc4.values()) else "")
    gain = (f"Fixing the top {rec.get('est_green_gain_clusters',0)} code-fixable clusters could clear "
            f"~<b>{rec.get('est_green_gain',0)}</b> files (~+{_pct(rec.get('est_green_gain',0),total)}% green).")
    return (f"<div class='head'><div class='bigrow'><div class='big'>{total} files</div>"
            f"<div>{pills}</div></div>"
            f"{badge_row}"
            f"<div class='note'>{len(rec.get('clusters',[]))} distinct clusters need work. {gain}</div></div>")


def _do_next(rec):
    rows = ["<h2>DO THIS NEXT — ranked by leverage (fix one cluster, every file in it flips)</h2>",
            "<table><tr><th>#</th><th>Problem (plain English)</th><th>Fix type</th><th>Who</th>"
            "<th>Files</th><th>%</th><th>Example file</th><th class='rc'>reason · layout</th></tr>"]
    total = rec.get("total_files", 0) or 1
    for i, g in enumerate(rec.get("clusters", []), 1):
        who_bg = WHO_COLOR.get(g["who"], "#f0f0f0")
        sev_bg = BUCKET_COLOR.get(g["severity"], "#fff")
        rows.append(
            f"<tr><td>{i}</td><td>{_esc(g['plain'])}</td>"
            f"<td><span class='tag' style='background:{sev_bg}'>{_esc(g['fix_type'])}</span></td>"
            f"<td><span class='tag' style='background:{who_bg}'>{_esc(g['who'])}</span></td>"
            f"<td>{g['count']}</td><td>{_pct(g['count'],total)}%</td>"
            f"<td class='mono'>{_esc(g['example'])}</td>"
            f"<td class='rc'>{_esc(g['reason_code'])} · {_esc(g['layout'])}</td></tr>")
    if not rec.get("clusters"):
        rows.append("<tr><td colspan='8' class='ok'>Nothing flagged — every file is GREEN. 🎉</td></tr>")
    rows.append("</table>")
    return "".join(rows)


def _gates(rec):
    mirror = rec.get("mirror", {})
    p = rec.get("products", {})
    uh = rec.get("unmapped_headers", {})
    nuh = len(uh.get("party", [])) + len(uh.get("stock", []))
    reg = rec.get("regression", [])
    rf = sum(r["failed"] for r in reg)
    items = [
        ("Move misfiled files (party ↔ stock)", len(rec.get("misfiled", [])), "run again with --apply-relocate"),
        ("Add unmapped headers to canonical.py", nuh, "editorial — see NEW_BATCH_RUNBOOK Step 2 (stays a candidate)"),
        ("Write product synonyms to catalog", p.get("synonym_candidates", 0), "run again with --apply-products"),
        ("Quarantine scanned/corrupt files", len(rec.get("quarantine", [])), "run again with --apply-quarantine"),
        ("Refresh regression baselines", rf, "only if the change was intentional: --update-baselines"),
    ]
    out = ["<h2>Needs your decision (nothing below was changed automatically)</h2>"]
    for label, n, how in items:
        out.append(f"<div class='gate'><b>{_esc(label)}:</b> {n} pending — "
                   f"<span class='muted'>{_esc(how)}</span></div>")
    sync = all(mirror.values()) if mirror else None
    if sync is not None:
        cls = "ok" if sync else "bad"
        txt = "IN SYNC" if sync else "DRIFT — reconcile Backends vs Python-Service-UI before deploy"
        detail = "  ".join(f"{k}:{'ok' if v else 'DIFF'}" for k, v in mirror.items())
        out.append(f"<div class='gate'>Engine mirror: <span class='{cls}'>{txt}</span> "
                   f"<span class='muted mono'>{_esc(detail)}</span></div>")
    return "".join(out)


def _panels(rec):
    out = []
    # triage by route
    rows = rec.get("triage_rows", [])
    by_route = {}
    for r in rows:
        d = by_route.setdefault(r["route"], {k: 0 for k, _, _ in BADGE})
        d[_badge_of(r)] += 1
    hdr = "".join(f"<th style='background:{col}'>{_esc(lbl)}</th>" for _, lbl, col in BADGE)
    trows = "".join(
        f"<tr><td class='mono'>{_esc(rt)}</td>"
        + "".join(f"<td>{d.get(k,0)}</td>" for k, _, _ in BADGE)
        + "</tr>" for rt, d in sorted(by_route.items()))
    out.append("<details><summary>Triage by route (4-state verdict)</summary><table>"
               "<tr><th>route</th>" + hdr + "</tr>" + trows + "</table></details>")

    # unmapped headers
    uh = rec.get("unmapped_headers", {})
    hrows = []
    for rt in ("party", "stock"):
        for it in uh.get(rt, [])[:60]:
            norm = it.get("norm") or it.get("header", "")
            cryptic = "⚠ open the file" if it.get("score", 0) < 0.5 or len(norm) <= 4 else ""
            hrows.append(f"<tr><td class='mono'>{_esc(rt)}</td><td class='mono'>{_esc(it['header'])}</td>"
                         f"<td>{it['count']}</td><td>{_esc(it['guess'])} ({it['score']})</td>"
                         f"<td class='mono'>{_esc(it.get('example',''))}</td><td>{cryptic}</td></tr>")
    out.append("<details><summary>Unmapped header candidates (canonical.py — editorial)</summary>"
               "<table><tr><th>type</th><th>header</th><th>files</th><th>closest field</th>"
               "<th>example</th><th></th></tr>" + "".join(hrows) + "</table></details>")

    # products
    p = rec.get("products", {})
    psample = "".join(f"<tr><td class='mono'>{_esc(k)}</td><td class='mono'>{_esc(', '.join(v[:6]))}</td></tr>"
                      for k, v in (p.get("added_sample") or {}).items())
    out.append("<details><summary>Product synonym candidates "
               f"({p.get('synonym_candidates',0)} across {p.get('products_touched',0)} products; "
               f"{p.get('unmatched',0)} new-product candidates)</summary>"
               f"<p class='muted'>Catalog: {p.get('catalog_size',0)} products. "
               f"{p.get('distinct_spellings',0)} distinct spellings seen, {p.get('noise',0)} rejected as noise.</p>"
               "<table><tr><th>canonical product</th><th>new spellings (sample)</th></tr>"
               + psample + "</table></details>")

    # regression
    reg = rec.get("regression", [])
    rrows = "".join(
        f"<tr><td class='mono'>{_esc(r['suite'])}</td><td>{r['passed']}</td><td>{r['failed']}</td>"
        f"<td class='mono'>{_esc(', '.join(f'{k}:{v}' for k,v in r.get('fields_moved',{}).items()))}</td></tr>"
        for r in reg)
    out.append("<details><summary>Regression (curated suites)</summary>"
               "<table><tr><th>suite</th><th>pass</th><th>fail</th><th>fields moved</th></tr>"
               + rrows + "</table></details>")

    # all files
    frows = []
    for r in sorted(rows, key=lambda x: ({"RED": 0, "ERROR": 1, "AMBER": 2, "GREEN": 3}.get(x["bucket"], 4),
                                         x["route"], x["reason_code"], x["file_name"])):
        meta = bc.fix_meta(r["reason_code"]) if r["bucket"] != "GREEN" else {"plain": "OK — extracted cleanly"}
        badge = _badge_of(r)
        frows.append(f"<tr style='background:{BADGE_COLOR.get(badge,'#fff')}'>"
                     f"<td class='mono'>{_file_link(r.get('path'), r['file_name'])}</td><td>{_esc(r['route'])}</td>"
                     f"<td>{_esc(BADGE_LABEL[badge])}<br><span class='rc'>{_esc(r['bucket'])}</span></td>"
                     f"<td>{_esc(meta['plain'])}</td>"
                     f"<td class='rc'>{_esc(r['reason_code'])}</td><td>{_esc(r.get('row_count'))}</td></tr>")
    out.append("<details><summary>All files ({} )</summary><table>"
               "<tr><th>file (stockist / slot / name)</th><th>route</th><th>verdict (4-state)</th><th>problem</th>"
               "<th class='rc'>reason</th><th>rows</th></tr>{}</table></details>".format(len(rows), "".join(frows)))
    return "".join(out)


def _legend():
    rows = []
    for rc, meta in bc.REASON_META.items():
        rows.append(f"<tr><td class='mono'>{_esc(rc)}</td><td>{_esc(meta[0])}</td>"
                    f"<td>{_esc(meta[1])}</td><td>{_esc(meta[2])}</td><td>{_esc(meta[3])}</td></tr>")
    return ("<details><summary>Legend — what each problem means &amp; who handles it</summary>"
            "<table><tr><th>reason code</th><th>plain English</th><th>fix type</th><th>who</th>"
            "<th>severity</th></tr>" + "".join(rows) + "</table></details>")


def render_html(rec: dict) -> str:
    return (
        "<!doctype html><meta charset='utf-8'><title>Batch dashboard — "
        + _esc(rec.get("batch")) + "</title><style>" + _CSS + "</style><div class='wrap'>"
        + f"<h1>Batch dashboard — {_esc(rec.get('batch'))}</h1>"
        + f"<p class='sub'>generated {_esc(rec.get('generated'))} · extract {rec.get('extract_seconds','?')}s · "
        + f"{rec.get('extract_errors',0)} unreadable</p>"
        + _headline(rec) + _do_next(rec) + _gates(rec)
        + "<h2>Details</h2>" + _panels(rec) + _legend()
        + "</div>")


def render(rec: dict, out_dir: Path) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    # SUMMARY first (simple, can't fail) so a dashboard-render issue never loses the digest
    (out_dir / "SUMMARY.md").write_text(render_summary(rec), encoding="utf-8")
    (out_dir / "dashboard.html").write_text(render_html(rec), encoding="utf-8")


if __name__ == "__main__":
    # render from a saved run.json (note: run.json omits per-file rows; dashboard
    # is normally written in-process by run_batch with the full record)
    rec = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    render(rec, Path(sys.argv[1]).parent)
    print("rendered", Path(sys.argv[1]).parent / "dashboard.html")
