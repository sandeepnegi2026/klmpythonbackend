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
from extractors.stock_xlsx.xlsx_io import load_data_sheets, workbook_kind


def extract(file_bytes: bytes, settings: dict | None = None) -> dict:
    started = time.perf_counter()
    settings = settings or {}
    filename = settings.get("filename", "")
    warnings = []
    layout = "tabular"
    sheet_name = None
    preview = ""
    pages_meta = []  # (page_no, line_count, char_count) per sheet/page
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
            fields = extract_header_fields(rows)
            for row in records:
                for key, value in fields.items():
                    row.setdefault(key, value)
            detected.update(header_detected_from_fields(fields))
            pages_meta.append((sheet_name or "html", len(rows), len(preview)))
        else:
            # A workbook may hold one data tab per division (COSMO, DERMA, ...). Parse EACH
            # tab on its own -- so every tab keeps its title/header at row 0 exactly as the
            # parsers expect -- then merge the clean records. load_data_sheets returns a
            # single tab for ordinary single-sheet books, so that path stays byte-identical.
            sheets = load_data_sheets(file_bytes, filename, settings.get("sheet_name"))
            records, detected, sheet_names, layouts, preview_parts = [], {}, [], [], []
            for name, srows in sheets:
                sheet_layout = detect_excel_layout(srows) if srows else "tabular"
                recs, det = parse_rows(srows, sheet_layout, settings.get("header_row"))
                if sheet_layout == "tabular" and not recs:
                    warnings.append("No stock header row found.")
                # Report-period / header fields are per-tab; stamp them on that tab's rows.
                fields = extract_header_fields(srows)
                for row in recs:
                    for key, value in fields.items():
                        row.setdefault(key, value)
                if det and not detected:
                    detected = dict(det)
                detected.update(header_detected_from_fields(fields))
                records.extend(recs)
                sheet_names.append(name)
                layouts.append(sheet_layout)
                # Preview = first 80 rows PLUS the tail (totals/footer region) of each tab,
                # disjointly, so the triage value-corroboration / total-reconcile checks see
                # every division's printed control totals instead of losing them past row 80.
                part = "\n".join(
                    "\t".join(row) for row in (srows[:80] + srows[80:][-12:])
                )
                preview_parts.append(part)
                pages_meta.append((name, len(srows), len(part)))
            preview = "\n".join(preview_parts)
            sheet_name = ",".join(sheet_names)
            layout = (
                layouts[0]
                if len(set(layouts)) <= 1 and layouts
                else ("mixed" if layouts else "tabular")
            )
    except Exception as exc:
        return {
            "rows": [],
            "headers_detected": {},
            "pages": [],
            "raw_text": "",
            "warnings": [str(exc)],
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
        }

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
    pages = [
        {
            "page_no": page_no,
            "char_count": char_count,
            "line_count": line_count,
            "rect_count": 0,
            "table_bboxes": [],
        }
        for page_no, line_count, char_count in pages_meta
    ]
    return {
        "rows": records,
        "headers_detected": detected,
        "pages": pages,
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
