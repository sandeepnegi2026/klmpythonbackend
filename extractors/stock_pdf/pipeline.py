import time

from extractors.stock_pdf.constants import LAYOUT_LABELS
from extractors.stock_pdf.detect import detect_layout
from extractors.stock_pdf.header_fields import extract_header_fields
from extractors.stock_pdf.layouts.generic import parse_generic
from extractors.stock_pdf.pdf_io import read_pdf_pages
from extractors.stock_pdf.postprocess import cast_numbers, sanity_warnings
from extractors.stock_pdf.registry import TEXT_PARSERS
from extractors.stock_pdf.table_io import parse_bordered

# Sanity-directed parse fallbacks (stock_pdf twin of party_pdf pdf_io._FALLBACKS,
# but triggered on RECONCILE FAILURE instead of an empty result). Used for layouts
# whose header is byte-identical to another vendor's export — no detect token can
# separate them (see the AMETOMBI note in detect.py) — but whose BODY the primary
# parser mis-maps (AMETOMBI's stray pack-count column shifts simple4's 4-number
# window and drops the real CLOSING). Each entry is (alt_layout, witness_token):
# the tolerant sibling is tried ONLY when
#   * the primary parse FAILED the stock reconcile identity
#     (pass_rate < 0.80 = triage sanity_red, on >= 5 checked rows), AND
#   * the vendor witness_token appears in the report head — REQUIRED because two
#     ANIL PHARMA baselines (DERMA 0.76 / PHARMA 0.58) ALSO fail simple4's
#     reconcile under the identical header, and their frozen baselines must not
#     move; 'ametombi' appears in 2/2280 corpus stock PDFs (the AMETOMBI books) —
# and adopted ONLY when the sibling reconciles >= 0.98 (triage sanity_green) on at
# least as many rows. Every file the primary already reconciles is byte-for-byte
# unaffected by construction.
_SANITY_FALLBACKS = {
    "simple4": (("stock_item_desc_oric_movement", "ametombi"),),
}
_SANITY_FALLBACK_TRIGGER = 0.80   # mirrors core.triage THRESHOLDS["sanity_red"]
_SANITY_FALLBACK_ACCEPT = 0.98    # mirrors core.triage THRESHOLDS["sanity_green"]
_SANITY_FALLBACK_MIN_ROWS = 5


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
        # Sanity-directed fallback (see _SANITY_FALLBACKS above): when the primary
        # layout parsed rows but they FAIL the stock reconcile identity, retry with
        # the header-identical tolerant sibling; adopt it only if it reconciles.
        if rows and layout in _SANITY_FALLBACKS:
            _, _s0 = sanity_warnings(rows)
            if (_s0["checked"] >= _SANITY_FALLBACK_MIN_ROWS
                    and _s0["pass_rate"] < _SANITY_FALLBACK_TRIGGER):
                _head = all_text[:3000].lower()
                for _alt_key, _witness in _SANITY_FALLBACKS[layout]:
                    if _witness and _witness not in _head:
                        continue
                    _alt = TEXT_PARSERS.get(_alt_key)
                    if _alt is None:
                        continue
                    _alt_rows = _alt(all_text)
                    if not _alt_rows:
                        continue
                    _, _s1 = sanity_warnings(_alt_rows)
                    if (_s1["checked"] >= _s0["checked"]
                            and _s1["pass_rate"] >= _SANITY_FALLBACK_ACCEPT
                            and _s1["pass_rate"] > _s0["pass_rate"]):
                        rows, layout = _alt_rows, _alt_key
                        break
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
