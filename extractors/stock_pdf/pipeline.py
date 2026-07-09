import time

from extractors.stock_pdf.constants import LAYOUT_LABELS
from extractors.stock_pdf.detect import detect_layout
from extractors.stock_pdf.header_fields import extract_header_fields
from extractors.stock_pdf.layouts.generic import parse_generic
from extractors.stock_pdf.pdf_io import read_pdf_pages
from extractors.stock_pdf.postprocess import cast_numbers, sanity_warnings
from extractors.stock_pdf.registry import TEXT_PARSERS
from extractors.stock_pdf.table_io import parse_bordered


def extract(file_bytes: bytes, settings: dict | None = None) -> dict:
    started = time.perf_counter()
    settings = settings or {}
    rows, headers_detected, warnings = [], {}, []

    all_text, pages, raw_parts, total_rects = read_pdf_pages(file_bytes, settings)
    header_fields = extract_header_fields(all_text)
    layout = detect_layout(all_text, total_rects)

    if layout in ("marg_bordered", "marg_web_stock", "prompt_bordered"):
        rows, headers_detected = parse_bordered(file_bytes, settings, layout)

    if not rows:
        parser = TEXT_PARSERS.get(layout, parse_generic)
        import inspect
        sig = inspect.signature(parser)
        if "file_bytes" in sig.parameters:
            rows = parser(all_text, file_bytes=file_bytes)
        else:
            rows = parser(all_text)
        headers_detected = (
            {
                f"text.{k}": k
                for k in [
                    "product_name",
                    "pack",
                    "opening_stock",
                    "purchase_stock",
                    "purchase_free",
                    "purchase_return",
                    "sales_qty",
                    "sales_value",
                    "sales_free",
                    "sales_return",
                    "closing_stock",
                    "closing_stock_value",
                    "rate",
                    "expiry",
                    "product_code",
                ]
                if any(k in r for r in rows[:1])
            }
            if rows
            else {}
        )

    if not rows:
        rows = parse_generic(all_text)

    for row in rows:
        for k, v in header_fields.items():
            row.setdefault(k, v)

    from core.pack_match import extract_pack_from_product
    from core.product_master import enrich_rows_with_master

    hd = {f"header.{k}": k for k, v in header_fields.items() if v}
    headers_detected.update(hd)
    
    for row in rows:
        if "product_name" in row:
            raw_full_name = str(row["product_name"])
            base_name, extracted_pack = extract_pack_from_product(raw_full_name)

            if layout == "stock_qoh_returns" and row.get("pack") and extracted_pack:
                # stock_qoh_returns splits the name against the printed
                # Packing column itself; re-peeling here is LOSSY for that
                # layout: pack is already set, so extracted_pack would be
                # discarded and the trailing dosage-form word silently
                # dropped from the name ('NIOFINE TAB' -> 'NIOFINE',
                # 'KLCEPO 200 TAB' -> 'KLCEPO'). Keep the layout's split.
                continue

            # Save original extracted fields
            row["product_name"] = base_name
            if base_name != raw_full_name:
                # Keep the full pre-strip name so enrichment can first try an exact
                # catalog hit on it (see core/product_master). setdefault: a fuller
                # name stashed by a layout parser wins.
                row.setdefault("_prestrip_name", raw_full_name)

            if not row.get("pack") and extracted_pack:
                row["pack"] = extracted_pack
                
    rows = enrich_rows_with_master(rows)
    cast_numbers(rows)
    from core.canonical import enforce_schema
    enforce_schema(rows, "stock")
    sw, sanity = sanity_warnings(rows)
    warnings.extend(sw)

    if not rows and not all_text.strip():
        warnings.append("No extractable text. This may be a scanned PDF requiring OCR.")
    elif not rows:
        warnings.append(f"No stock rows extracted. Detected layout: {layout}")

    return {
        "rows": rows,
        "headers_detected": headers_detected,
        "pages": pages,
        "raw_text": "\n".join(raw_parts),
        "warnings": warnings,
        "sanity": sanity,
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
        "debug": {
            "parser": "stock_pdf",
            "layout": layout,
            "layout_label": LAYOUT_LABELS.get(layout, layout),
            "row_count": len(rows),
            "total_rects": total_rects,
        },
    }
