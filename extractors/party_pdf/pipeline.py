from core.header_match import map_headers
from core.pack_match import extract_pack_from_product
from core.product_master import enrich_rows_with_master

from extractors.party_pdf.pdf_io import extract_pdf


def _canonicalize_rows(headers, rows):
    header_map = map_headers(headers, "party")
    detected = {raw: info["canonical"] for raw, info in header_map.items()}
    canonical_rows = []
    for row in rows:
        record = {}
        for idx, raw_header in enumerate(headers):
            canonical_key = detected.get(str(raw_header))
            if canonical_key and idx < len(row):
                record[canonical_key] = row[idx]
        if record:
            canonical_rows.append(record)
    return canonical_rows, detected


def extract(file_bytes, settings=None):
    legacy = extract_pdf(file_bytes)
    headers = legacy.get("parsed_headers", []) or []
    rows = legacy.get("parsed_rows", []) or []
    canonical_rows, headers_detected = _canonicalize_rows(headers, rows)
    
    for record in canonical_rows:
        if "product_name" in record:
            raw_full_name = str(record["product_name"])
            base_name, extracted_pack = extract_pack_from_product(raw_full_name)
            
            # Save original extracted fields
            record["product_name"] = base_name
            if base_name != raw_full_name:
                # Keep the full pre-strip name so enrichment can first try an exact
                # catalog hit on it (see core/product_master). setdefault: a fuller
                # name stashed by a layout parser wins.
                record.setdefault("_prestrip_name", raw_full_name)

            if not record.get("pack") and extracted_pack:
                record["pack"] = extracted_pack
                
    canonical_rows = enrich_rows_with_master(canonical_rows)

    warnings = []
    if legacy.get("parse_error"):
        warnings.append(legacy["parse_error"])
    pages = []
    raw_parts = []
    for page in legacy.get("pages", []) or []:
        text = page.get("text", "") or ""
        raw_parts.append(text)
        pages.append(
            {
                "page_no": page.get("page_number"),
                "char_count": page.get("char_count", len(text)),
                "line_count": page.get("line_count", 0),
                "rect_count": page.get("rect_count", 0),
                "table_bboxes": [],
            }
        )
    from core.canonical import enforce_schema
    enforce_schema(canonical_rows, "party")

    return {
        "rows": canonical_rows,
        "headers_detected": headers_detected,
        "pages": pages,
        "raw_text": "\n".join(raw_parts),
        "warnings": warnings,
        "elapsed_ms": legacy.get("runtime_ms", 0),
        "debug": {
            "parser": "party_pdf",
            "layout": legacy.get("detected_format"),
            "detected_format": legacy.get("detected_format"),
            "format_label": legacy.get("format_label"),
            "layout_label": legacy.get("format_label"),
            "row_count": len(canonical_rows),
        },
    }
