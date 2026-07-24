import time

from core.pack_match import extract_pack_from_product
from core.party_filter import tag_generic_accounts
from core.product_master import enrich_rows_with_master
from extractors.party_xlsx.constants import LAYOUT_LABELS
from extractors.party_xlsx.detect import detect_layout
from extractors.party_xlsx.layouts.swil_html_billwise import (
    detect as detect_swil_html_billwise,
    parse_swil_html_billwise,
)
from extractors.party_xlsx.postprocess import cast_numbers
from extractors.party_xlsx.registry import parse_rows
from extractors.party_xlsx.xlsx_io import load_data_sheets, read_sheets, sheet_rows_from_df

import re as _re

_TABLE_SHEET_RE = _re.compile(r"table\s*\d+$", _re.I)


def _is_raja_party_summary(sheets):
    """True if the kept tabs are the RAJA "Table N" converter's PARTY/ITEM WISE SALES SUMMARY.
    The Table-N sheet naming is what separates this paginated converter from the many other
    'item wise sales summary' party exports, so those are never stolen."""
    if not sheets or not all(_TABLE_SHEET_RE.match(name.strip()) for name, _ in sheets):
        return False
    flat = " ".join(
        " ".join(cell for cell in row) for _name, rows in sheets for row in rows[:120]
    ).lower().replace(" ", "")
    return "party/itemwisesalessummary" in flat


def _concat_table_sheets(file_bytes, filename):
    """All sheets' rows in workbook order, but only for a paginated (>= 2 sheet) book — the
    RAJA converter splits ONE report across many 'Table N' pages that load_data_sheets' per-tab
    scoring would otherwise drop."""
    xls, _ = read_sheets(file_bytes, filename)
    if len(xls.sheet_names) < 2:
        return None
    merged = []
    for name in xls.sheet_names:
        merged.extend(sheet_rows_from_df(xls.parse(name, header=None)))
    return merged


def extract(file_bytes, settings=None):
    started = time.perf_counter()
    settings = settings or {}
    filename = settings.get("filename", "")
    warnings = []
    # SwilERP party-billwise exports ship as an HTML document saved with a .xls
    # extension; pandas/xlrd read them as 0 rows (-> RED SCANNED_OR_EMPTY). Route them,
    # BEFORE the spreadsheet reader, to the dedicated HTML parser. The gate fires only on
    # HTML bytes carrying the SwilERP party-billwise header (Customer Name + BillNo +
    # Total Sales), so a real .xlsx/.xls never enters this branch and stays byte-identical.
    if detect_swil_html_billwise(file_bytes):
        return _extract_html(file_bytes, started)
    try:
        sheets = load_data_sheets(file_bytes, filename, settings.get("sheet_name"))
    except Exception as exc:
        return {
            "rows": [],
            "headers_detected": {},
            "pages": [],
            "raw_text": "",
            "warnings": [str(exc)],
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
        }

    # A workbook may hold one data tab per division (COSMO, DERMA, ...). Parse EACH tab on
    # its own -- so every tab keeps its title/header at row 0 exactly as the parsers expect --
    # then merge the clean records. load_data_sheets returns a single tab for ordinary
    # single-sheet books, so that path stays byte-identical to before.
    # RAJA ENTERPRISE "PARTY / ITEM WISE SALES SUMMARY" is paginated across many "Table N"
    # sheets; per-tab scoring drops continuation pages. If the kept tabs carry its signature and
    # the book is multi-sheet, re-read every tab raw, collapse to one synthetic sheet, and FORCE
    # the raja parser (which reconciles to the printed grand TOTAL qty/amount).
    forced = None
    if _is_raja_party_summary(sheets):
        merged = _concat_table_sheets(file_bytes, filename)
        if merged is not None:
            sheets = [("merged", merged)]
            forced = "raja_party_item_summary"

    records, detected, sheet_names, layouts = [], {}, [], []
    for name, srows in sheets:
        sheet_layout = forced or detect_layout(srows)
        recs, det = parse_rows(srows, sheet_layout)
        if not recs and sheet_layout != "tabular":
            recs, det = parse_rows(srows, "tabular")
        records.extend(recs)
        if det and not detected:
            detected = det
        sheet_names.append(name)
        layouts.append(sheet_layout)
    # Line-accounting ledger on the FULL raw sheets (immune to the 80+tail raw_text
    # preview truncation) against the raw pre-cast records. Read-only.
    from core.line_ledger import audit_sheet_rows
    try:
        line_audit = audit_sheet_rows(sheets, records)
    except Exception:  # ledger must never break extraction
        line_audit = {"applicable": False, "reason": "ledger error"}
    # TAG generic non-customer ledger accounts (CASH / COUNTER / WALK IN / STAFF / ...) with
    # is_generic_party=True instead of DROPPING them — all rows are retained so totals stay
    # complete, and party-wise reads exclude them at query time. Runs AFTER the ledger. Same
    # name-anchored allowlist (core/party_filter) — a real shop is never tagged.
    records, _generic_tagged = tag_generic_accounts(records)
    cast_numbers(records)
    sheet_name = ",".join(sheet_names)
    layout = (
        layouts[0]
        if len(set(layouts)) <= 1 and layouts
        else ("mixed" if layouts else "tabular")
    )
    
    for row in records:
        if "product_name" in row:
            raw_full_name = str(row["product_name"])
            base_name, extracted_pack = extract_pack_from_product(raw_full_name)
            
            # Save original extracted fields
            row["product_name"] = base_name
            if base_name != raw_full_name:
                # Keep the full pre-strip name so enrichment can first try an exact
                # catalog hit on it (see core/product_master). setdefault: a fuller
                # name stashed by a layout parser wins.
                row.setdefault("_prestrip_name", raw_full_name)

            if not row.get("pack") and extracted_pack:
                row["pack"] = extracted_pack
                
    records = enrich_rows_with_master(records)

    if not records:
        warnings.append(f"No party rows extracted (layout={layout}, sheet={sheet_name}).")
    # Preview = first 80 rows PLUS the tail (grand-total footer) of EACH tab, so the triage
    # total-reconcile check can see every division's printed "Grand Total" instead of losing it
    # past row 80 (mirrors extractors/stock_xlsx/pipeline.py). raw_text is not part of any
    # regression snapshot, so this only affects triage bucketing, never extracted rows.
    pages, preview_parts = [], []
    for name, srows in sheets:
        part = "\n".join("\t".join(row) for row in (srows[:80] + srows[80:][-12:]))
        preview_parts.append(part)
        pages.append(
            {
                "page_no": name,
                "char_count": len(part),
                "line_count": len(srows),
                "rect_count": 0,
                "table_bboxes": [],
            }
        )
    preview = "\n".join(preview_parts)
    from core.canonical import enforce_schema
    enforce_schema(records, "party")

    return {
        "rows": records,
        "headers_detected": detected,
        "pages": pages,
        "raw_text": preview,
        "warnings": warnings,
        "line_audit": line_audit,
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
        "debug": {
            "layout": layout,
            "layout_label": LAYOUT_LABELS.get(layout, layout),
            "sheet": sheet_name,
            "generic_party_rows_tagged": _generic_tagged,
        },
    }


def _extract_html(file_bytes, started):
    """Parse a SwilERP party-billwise HTML-in-.xls export, then run the SAME postprocess
    (pack split -> master enrichment -> cast_numbers -> enforce_schema) as the spreadsheet
    path so the records are shaped identically to every other party_xlsx layout."""
    from core.canonical import enforce_schema

    layout = "swil_html_billwise"
    warnings = []
    records, detected = parse_swil_html_billwise(file_bytes)
    records, _ = tag_generic_accounts(records)

    for row in records:
        if "product_name" in row:
            raw_full_name = str(row["product_name"])
            base_name, extracted_pack = extract_pack_from_product(raw_full_name)
            row["product_name"] = base_name
            if base_name != raw_full_name:
                row.setdefault("_prestrip_name", raw_full_name)
            if not row.get("pack") and extracted_pack:
                row["pack"] = extracted_pack

    records = enrich_rows_with_master(records)
    cast_numbers(records)
    enforce_schema(records, "party")

    if not records:
        warnings.append(f"No party rows extracted (layout={layout}).")

    text = file_bytes.decode("utf-8-sig", errors="replace")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    preview = "\n".join(lines)[:4000]
    pages = [
        {
            "page_no": "html",
            "char_count": len(preview),
            "line_count": len(lines),
            "rect_count": 0,
            "table_bboxes": [],
        }
    ]
    return {
        "rows": records,
        "headers_detected": detected,
        "pages": pages,
        "raw_text": preview,
        "warnings": warnings,
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
        "debug": {
            "layout": layout,
            "layout_label": LAYOUT_LABELS.get(layout, layout),
            "sheet": "html",
        },
    }
