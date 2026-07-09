import time

from core.pack_match import extract_pack_from_product
from core.product_master import enrich_rows_with_master
from extractors.party_xlsx.constants import LAYOUT_LABELS
from extractors.party_xlsx.detect import detect_layout
from extractors.party_xlsx.postprocess import cast_numbers
from extractors.party_xlsx.registry import parse_rows
from extractors.party_xlsx.xlsx_io import load_rows


def extract(file_bytes, settings=None):
    started = time.perf_counter()
    settings = settings or {}
    filename = settings.get("filename", "")
    warnings = []
    try:
        sheet_name, rows = load_rows(file_bytes, filename, settings.get("sheet_name"))
    except Exception as exc:
        return {
            "rows": [],
            "headers_detected": {},
            "pages": [],
            "raw_text": "",
            "warnings": [str(exc)],
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
        }

    layout = detect_layout(rows)
    records, detected = parse_rows(rows, layout)
    if not records and layout != "tabular":
        records, detected = parse_rows(rows, "tabular")
    cast_numbers(records)
    
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
    # Preview = first 80 rows PLUS the tail (grand-total footer) of any larger sheet, so the
    # triage total-reconcile check can see the printed "Grand Total" instead of losing it past
    # row 80 (mirrors extractors/stock_xlsx/pipeline.py). raw_text is not part of any regression
    # snapshot, so this only affects triage bucketing, never extracted rows.
    preview = "\n".join("\t".join(row) for row in (rows[:80] + rows[80:][-12:]))
    from core.canonical import enforce_schema
    enforce_schema(records, "party")

    return {
        "rows": records,
        "headers_detected": detected,
        "pages": [
            {
                "page_no": sheet_name,
                "char_count": len(preview),
                "line_count": len(rows),
                "rect_count": 0,
                "table_bboxes": [],
            }
        ],
        "raw_text": preview,
        "warnings": warnings,
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
        "debug": {
            "layout": layout,
            "layout_label": LAYOUT_LABELS.get(layout, layout),
            "sheet": sheet_name,
        },
    }
