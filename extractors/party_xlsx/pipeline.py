import time

from core.pack_match import extract_pack_from_product
from core.product_master import enrich_rows_with_master
from extractors.party_xlsx.constants import LAYOUT_LABELS
from extractors.party_xlsx.detect import detect_layout
from extractors.party_xlsx.postprocess import cast_numbers
from extractors.party_xlsx.registry import parse_rows
from extractors.party_xlsx.xlsx_io import load_data_sheets


def extract(file_bytes, settings=None):
    started = time.perf_counter()
    settings = settings or {}
    filename = settings.get("filename", "")
    warnings = []
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
    records, detected, sheet_names, layouts = [], {}, [], []
    for name, srows in sheets:
        sheet_layout = detect_layout(srows)
        recs, det = parse_rows(srows, sheet_layout)
        if not recs and sheet_layout != "tabular":
            recs, det = parse_rows(srows, "tabular")
        records.extend(recs)
        if det and not detected:
            detected = det
        sheet_names.append(name)
        layouts.append(sheet_layout)
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
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
        "debug": {
            "layout": layout,
            "layout_label": LAYOUT_LABELS.get(layout, layout),
            "sheet": sheet_name,
        },
    }
