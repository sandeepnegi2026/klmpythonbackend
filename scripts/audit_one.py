"""Forensic per-file extraction auditor — completeness + correctness, not just GREEN.

See EXTRACTION_AUDIT_RUNBOOK.md. GREEN triage only proves the KEPT rows reconcile; this
runs three independent oracles (line census, printed totals, reconcile) so dropped rows
and silent column mis-maps cannot hide behind a green badge.

    python scripts/audit_one.py "<file>" stock_pdf
    python scripts/audit_one.py "<file>" stock_pdf --force-layout stock_simple_7col
"""
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pdfplumber  # noqa: E402

from scripts.batch_extract import ROUTES, report_type  # noqa: E402
from core.quality import build_quality  # noqa: E402
from extractors.stock_pdf.registry import TEXT_PARSERS  # noqa: E402

_NOISE = re.compile(
    r'^\s*$'
    r'|^\s*page\b|\bpage\s*\d|\bpage\s*:\s*\d'
    r'|grand\s*total|^\s*total\b|group\s*total|\btotal\s*:'
    r'|^\s*[-=_*]{3,}\s*$'
    r'|powered by|taken by|taken at'
    r'|^gstin|^tin\b|^phone|^e-?mail|^\d+\s*[b:]'                 # licence/GSTIN block
    r'|stock\s*(and|&)\s*sales?\s*(statement|report|analysis)'    # report title banner
    r'|^(opening|purchase|sales|closing)(\s+(value|return|stock))?\s+[\d,]+\.?\d*\s*$'  # top summary block
    r'|^\d[\d/\-,\s]*(floor|street|st\b|road|nagar|complex|colony|market|varal|near)'    # address line
    r'|\bdiv\b\s*$|\[\d+\]\s*$'                                   # division bands
    r'|item\s*name|product\s*/?\s*(name|company)|^no\b.*\bproduct',  # column-header row
    re.I,
)


def _norm(s):
    return re.sub(r'[^A-Z0-9]', '', s.upper())


def candidate_data_lines(raw_text):
    out = []
    for ln in raw_text.splitlines():
        s = ln.strip()
        if not s or _NOISE.search(s):
            continue
        if re.search(r'[A-Za-z]', s) and re.search(r'\d', s):
            out.append(s)
    return out


def _line_matches_a_row(line, norm_names):
    """A candidate line matches an output row if the line's leading product token
    (the first alpha run >=4 chars) appears inside a normalized output name."""
    toks = re.findall(r'[A-Za-z]{4,}', line.upper())
    if not toks:
        toks = re.findall(r'[A-Za-z]{3,}', line.upper())
    if not toks:
        return True  # no name token -> not a product line, don't flag
    key = toks[0]
    return any(key in n for n in norm_names)


def printed_totals(raw_text):
    hits = []
    for ln in raw_text.splitlines():
        if re.search(r'grand\s*total|group\s*total|^\s*total\b|\btotal\s*:', ln, re.I):
            nums = re.findall(r'-?\d[\d,]*\.?\d*', ln)
            if nums:
                hits.append((ln.strip(), [float(n.replace(',', '')) for n in nums]))
    return hits


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def audit(path, route, force_layout=None):
    fb = open(path, "rb").read()
    if force_layout:
        with pdfplumber.open(io.BytesIO(fb)) as pdf:
            text = "\n".join((p.extract_text() or "") for p in pdf.pages)
        parser = TEXT_PARSERS[force_layout]
        import inspect
        if "file_bytes" in inspect.signature(parser).parameters:
            rows = parser(text, file_bytes=fb)
        else:
            rows = parser(text)
        res = {"rows": rows, "layout": force_layout, "layout_label": "(forced)"}
    else:
        res = ROUTES[route](fb)
    rows = res.get("rows", [])
    rtype = report_type(route)
    try:
        q = build_quality(res, rtype)
        bucket = q["triage"]["bucket"] + " " + q["triage"]["reason_code"]
    except Exception as exc:  # noqa: BLE001
        bucket = f"(build_quality failed: {exc})"

    print("FILE   :", os.path.basename(path))
    print("LAYOUT :", res.get("layout"), "|", str(res.get("layout_label", ""))[:60])
    print("VERDICT:", bucket, "| output rows:", len(rows))

    raw = ""
    if path.lower().endswith(".pdf"):
        with pdfplumber.open(io.BytesIO(fb)) as pdf:
            raw = "\n".join((p.extract_text() or "") for p in pdf.pages)

    # Oracle A --------------------------------------------------------------
    cands = candidate_data_lines(raw)
    print(f"\nORACLE A (completeness)  candidate lines={len(cands)}  rows={len(rows)}  "
          f"DELTA={len(cands) - len(rows)}")
    norm_names = [_norm(str(r.get("product_name", ""))) for r in rows]
    missing = [s for s in cands if not _line_matches_a_row(s, norm_names)]
    if missing:
        print(f"  !! {len(missing)} candidate line(s) with NO matching output row (DROPPED?):")
        for s in missing[:15]:
            print("     MISSING:", s[:82])
    else:
        print("  OK: every candidate line has a matching output row")

    # Oracle B --------------------------------------------------------------
    print("\nORACLE B (printed totals)")
    for ln, nums in printed_totals(raw):
        print("   printed:", ln[:88], "->", nums)
    for f in ("opening_stock", "purchase_stock", "sales_qty", "closing_stock",
              "sales_value", "closing_stock_value"):
        tot = sum(_f(r.get(f)) for r in rows)
        if tot:
            print(f"   sum({f}) = {round(tot, 2)}")

    # Oracle C --------------------------------------------------------------
    bad = chk = 0
    for r in rows:
        v = {k: _f(r.get(k)) for k in
             ("opening_stock", "purchase_stock", "purchase_free", "purchase_return",
              "sales_qty", "sales_free", "sales_return", "closing_stock")}
        if all(x == 0 for x in v.values()):
            continue
        chk += 1
        base = (v["opening_stock"] + v["purchase_stock"] + v["purchase_free"]
                - v["purchase_return"] - v["sales_qty"] - v["sales_free"] + v["sales_return"])
        if abs(base - v["closing_stock"]) > 0.05 * max(abs(v["closing_stock"]), 1):
            bad += 1
    print(f"\nORACLE C (reconcile)  non-phantom={chk}  bad={bad}")

    print("\nSAMPLE ROWS (compare cell-by-cell to the PDF):")
    for r in rows[:8]:
        print("  ", {k: r.get(k) for k in
              ("product_name", "pack", "opening_stock", "purchase_stock", "sales_qty",
               "sales_value", "closing_stock", "closing_stock_value")})


if __name__ == "__main__":
    _force = None
    if "--force-layout" in sys.argv:
        i = sys.argv.index("--force-layout")
        _force = sys.argv[i + 1]
    audit(sys.argv[1], sys.argv[2], _force)
