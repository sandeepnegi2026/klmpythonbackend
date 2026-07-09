import time

from extractors.stock_xlsx.constants import LAYOUT_LABELS
from extractors.stock_xlsx.detect import detect_excel_layout
from extractors.stock_xlsx.header_fields import (
    extract_header_fields,
    header_detected_from_fields,
)
from extractors.stock_xlsx.layouts.html_stock import parse_html_stock_table
from extractors.stock_xlsx.postprocess import cast_numbers, sanity_warnings
from extractors.stock_xlsx.registry import parse_rows
from extractors.stock_xlsx.xlsx_io import load_rows, workbook_kind


def extract(file_bytes: bytes, settings: dict | None = None) -> dict:
    started = time.perf_counter()
    settings = settings or {}
    filename = settings.get("filename", "")
    warnings = []
    layout = "tabular"
    sheet_name = None
    rows = []
    sanity = {"checked": 0, "failed": 0, "passed": 0, "pass_rate": 0.0}
    try:
        kind = workbook_kind(file_bytes, filename)
        if kind == ".html":
            text = file_bytes.decode("utf-8-sig", errors="replace")
            records, detected = parse_html_stock_table(file_bytes)
            layout = "html_stock"
            rows = [[line.strip()] for line in text.splitlines() if line.strip()][:150]
            preview = "\n".join(
                line.strip() for line in text.splitlines() if line.strip()
            )[:4000]
        else:
            sheet_name, rows = load_rows(file_bytes, filename, settings.get("sheet_name"))
            layout = detect_excel_layout(rows) if rows else "tabular"
            records, detected = parse_rows(rows, layout, settings.get("header_row"))
            if layout == "tabular" and not records:
                warnings.append("No stock header row found.")
            # Preview = first 80 rows PLUS the tail (totals/footer region) of any larger
            # sheet, disjointly. A big book (e.g. 300 rows) prints its grand-totals in the
            # last rows; keeping them lets the triage value-corroboration / total-reconcile
            # checks see the printed control totals instead of losing them past row 80.
            head = rows[:80]
            tail = rows[80:][-12:]
            preview = "\n".join("\t".join(row) for row in head + tail)
    except Exception as exc:
        return {
            "rows": [],
            "headers_detected": {},
            "pages": [],
            "raw_text": "",
            "warnings": [str(exc)],
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
        }

    fields = extract_header_fields(rows)
    for row in records:
        for key, value in fields.items():
            row.setdefault(key, value)
    detected.update(header_detected_from_fields(fields))
    
    from core.pack_match import extract_pack_from_product
    from core.product_master import enrich_rows_with_master
    
    for row in records:
        if "product_name" in row and not row.get("pack"):
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
    cast_numbers(records)
    from core.canonical import enforce_schema
    enforce_schema(records, "stock")
    sanity_warnings_list, sanity = sanity_warnings(records)
    warnings.extend(sanity_warnings_list)
    if not records and layout != "html_stock":
        warnings.append(f"No stock rows extracted (layout={layout}, sheet={sheet_name}).")
    return {
        "rows": records,
        "headers_detected": detected,
        "pages": [
            {
                "page_no": sheet_name or "html",
                "char_count": len(preview),
                "line_count": len(rows),
                "rect_count": 0,
                "table_bboxes": [],
            }
        ],
        "raw_text": preview,
        "warnings": warnings,
        "sanity": sanity,
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
        "debug": {
            "parser": "stock_xlsx",
            "layout": layout,
            "layout_label": LAYOUT_LABELS.get(layout, layout),
            "sheet": sheet_name,
            "row_count": len(records),
        },
    }
