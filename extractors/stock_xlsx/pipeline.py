import re
import time

from extractors.stock_xlsx.constants import LAYOUT_LABELS
from extractors.stock_xlsx.detect import detect_excel_layout
from extractors.stock_xlsx.header_fields import (
    extract_header_fields,
    header_detected_from_fields,
)
from extractors.stock_xlsx.layouts.html_stock import parse_html_stock_table
from extractors.stock_xlsx.layouts.purani_mfr_stock_sales import parse_purani_mfr_stock_sales
from extractors.stock_xlsx.postprocess import cast_numbers, sanity_warnings
from extractors.stock_xlsx.registry import parse_rows
from extractors.stock_xlsx.xlsx_io import load_data_sheets, read_sheets, sheet_rows, workbook_kind


# ---------------------------------------------------------------------------
# Sanity-directed dispatch fallback (header-identical trap escape hatch).
#
# Some vendors ship TOKEN-IDENTICAL headers over structurally different grids
# (e.g. ANNAPURNA vs MINERVA "Stock and Sales Mfac Group Wise Report": same
# title + Item/Bal/BVal/SVal header, 28-col vs 59-col body), so no detect-time
# token can route them apart. This hook routes by OUTCOME instead: when the
# generic `tabular` read fails stock sanity on most rows AND a registered
# candidate's cheap header predicate matches, the file is re-extracted once
# with the candidate layout forced, and the alternative is adopted ONLY if it
# is decisively better (>=0.90 sanity pass rate, comparable row count). A
# wrong candidate can therefore never replace a working tabular read — a
# MINERVA-style twin is rejected on its own outcome (0.72 < 0.90) even if its
# predicate matched.
#
# Each entry: (layout_name, predicate(sheets)) where sheets is the
# load_data_sheets() list of (name, rows). Predicates must be cheap and
# narrow; they only SHORTLIST a candidate — the sanity comparison decides.
# ---------------------------------------------------------------------------

def _mfac_group_wise_gate(sheets):
    """KLM / C-Square PharmAssist abbreviated Mfac stock grid — the whole family:
    ANNAPURNA ('Stock and Sales Mfac Group Wise Report'), MINERVA (token-identical 59-col
    book), KOOTTIPARAMBIL, BIO PHARMA ('Stock and Sale Report'), ... all carrying the
    Item | Op. | Pur | SP | Sale | SS | Br | Cr | Db | Adj | Bal. | BVal | SVal header.
    Shortlisted on the distinctive BVal+SVal (balance-value + sales-value) abbreviation
    pair, which is unique to this C-Square export and appears in no other stock family.
    The neighbouring title / column-width differences (Mfac-Group-Wise vs plain, 28 vs
    59 cols, apr/may vs jan/feb prev-month labels) rename per vendor/month, so they can't
    route the family apart -- but this is only a SHORTLIST: the pipeline still adopts the
    mfac parse ONLY when it reconciles >= 0.90 and keeps >= 80% of the rows, so a
    non-member that happens to carry these tokens can never displace its working read."""
    for _name, srows in sheets:
        if not srows:
            continue
        flat = " ".join(" ".join(r) for r in srows[:150]).lower().replace(" ", "")
        if "bval" in flat and "sval" in flat:
            return True
    return False


SANITY_FALLBACKS = [
    ("klm_mfac_group_wise_stock", _mfac_group_wise_gate),
]

# Trigger: only a mostly-failing tabular read is ever reconsidered.
_FALLBACK_MIN_CHECKED = 10          # need a real sample, not a 3-row stub
_FALLBACK_TRIGGER_PASS_RATE = 0.50  # tabular failed sanity on >= half the rows
# Acceptance: the candidate must be decisively good, not merely "less bad".
_FALLBACK_ACCEPT_PASS_RATE = 0.90
_FALLBACK_MIN_ROW_RATIO = 0.80      # candidate must keep >= 80% of tabular's rows


_TABLE_SHEET_RE = re.compile(r"table\s*\d+$", re.I)


def _ssa_variant(sheets):
    """Which paginated 'STOCK & SALES ANALYSIS' converter variant, if any, the kept tabs carry.
    Cheap check on the already-loaded tabs; only then do we re-read every tab raw. Returns the
    forced layout id, or None.
      - sale+value banner '<===sale===>'  -> sm_stock_sales_analysis   (S.M. MEDICAL)
      - Opening/Receipt/Issue/Closing qty -> raja_stock_oric_analysis  (RAJA ENTERPRISE)

    This converter names EVERY page 'Table 1'..'Table N'. A Marg ERP 9+ export is ALSO titled
    'STOCK & SALES ANALYSIS' with Opening/Receipt/Issue/Closing columns, but names its sheets
    'MARG ERP 9+ Excel Report'/'Sheet2' — so the Table-N sheet naming is the discriminator that
    keeps the raja_oric gate from stealing the whole Marg family."""
    if not sheets or not all(_TABLE_SHEET_RE.match(name.strip()) for name, _ in sheets):
        return None
    flat = " ".join(
        " ".join(cell for cell in row) for _name, rows in sheets for row in rows[:120]
    ).lower().replace(" ", "")
    if "stock&salesanalysis" not in flat:
        return None
    if "<===sale===>" in flat:
        return "sm_stock_sales_analysis"
    if "openingreceiptissueclosing" in flat:
        return "raja_stock_oric_analysis"
    return None


def _concat_if_paginated(file_bytes, filename):
    """Concatenate every sheet's rows IN WORKBOOK ORDER, but only for a genuinely PAGINATED
    book (>= 2 sheets). Returns the merged rows, or None for a single-sheet workbook.

    The S.M. converter paginates ONE "STOCK & SALES ANALYSIS" report across many "Table N"
    sheets, and load_data_sheets' per-tab scoring drops continuation pages — so we read the
    whole book. But single-sheet exports of the same sale+value converter (BALLRI COSMOQ,
    SAM MEDICOS) are already handled correctly by marg_sale_closing_*; the >= 2 sheet guard
    leaves those on the normal per-sheet path untouched."""
    xls, _ = read_sheets(file_bytes, filename)
    if len(xls.sheet_names) < 2:
        return None
    merged = []
    for name in xls.sheet_names:
        merged.extend(sheet_rows(xls.parse(name, header=None)))
    return merged


def extract(file_bytes: bytes, settings: dict | None = None) -> dict:
    started = time.perf_counter()
    settings = settings or {}
    filename = settings.get("filename", "")
    forced_layout = settings.get("_forced_layout")  # sanity-fallback re-entry only
    warnings = []
    layout = "tabular"
    sheet_name = None
    preview = ""
    pages_meta = []  # (page_no, line_count, char_count) per sheet/page
    sheets_ref = None  # raw (name, rows) list, kept for the sanity-fallback gate
    sanity = {"checked": 0, "failed": 0, "passed": 0, "pass_rate": 0.0}
    try:
        kind = workbook_kind(file_bytes, filename)
        if kind == ".html":
            text = file_bytes.decode("utf-8-sig", errors="replace")
            # PURANI HOSPITAL SUPPLIES "MFR Stock and Sales Report" ships an 18-col HTML-in-.xls
            # (Particulars|Pack|O.St|Pur|Free|PRtn|Mon|C.St|...) that the legacy html_stock reader
            # cannot column-split. Route it to the dedicated parser; tokens 'mfr stock and sales
            # report'/'prtn'/'mbmon' appear in no other html_stock export, so nothing else is stolen.
            low = text.lower()
            if "mfr stock and sales report" in low or ("particulars" in low and "prtn" in low and "mbmon" in low):
                records, detected = parse_purani_mfr_stock_sales(file_bytes)
                layout = "purani_mfr_stock_sales"
            else:
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
            # S.M. MEDICAL converter "STOCK & SALES ANALYSIS" is paginated across many "Table N"
            # sheets; per-tab scoring drops continuation pages (keeps 19/28 -> 97 of 312 rows).
            # If the kept tabs carry its unique SALE-banner signature AND the book is genuinely
            # multi-sheet, re-read EVERY tab raw, collapse to one synthetic sheet, and FORCE the
            # sm parser (which reconciles to the printed grand TOTAL). Single-sheet siblings stay
            # on the normal per-sheet path (already handled by marg_sale_closing_*).
            sm_forced = None
            if forced_layout is None:
                _variant = _ssa_variant(sheets)
                if _variant:
                    merged = _concat_if_paginated(file_bytes, filename)
                    if merged is not None:
                        sheets = [("merged", merged)]
                        sm_forced = _variant
            sheets_ref = sheets
            records, detected, sheet_names, layouts, preview_parts = [], {}, [], [], []
            for name, srows in sheets:
                sheet_layout = forced_layout or sm_forced or (detect_excel_layout(srows) if srows else "tabular")
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
                head_tail = srows[:80] + srows[80:][-12:]
                # A Prompt "Stock Statement (Datewise)" packs ALL 5-7 KLM divisions into ONE
                # sheet, each ending with its own mid-sheet "Total:"/"Amount:" footer pair. The
                # head+tail preview drops those interior footers, so triage's total-reconcile
                # can't see them and flags a spurious TOTAL_MISMATCH though extraction is perfect.
                # Additively re-include ONLY the per-division footer LABEL rows from the dropped
                # middle, in document order. Gated on this exact layout + a sheet long enough to
                # have a dropped middle, so every other layout/short sheet stays byte-identical.
                if sheet_layout == "prompt_dstk_free_xlsx" and len(srows) > 92:
                    import re as _re
                    _foot = _re.compile(r"^(?:grand\s*total|total|amount)\s*:?\s*$", _re.I)
                    kept_mid = [
                        row for row in srows[80: len(srows) - 12]
                        if any(_foot.match(cell.strip()) for cell in row if cell.strip())
                    ]
                    if kept_mid:
                        head_tail = srows[:80] + kept_mid + srows[80:][-12:]
                part = "\n".join("\t".join(row) for row in head_tail)
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

    # Line-accounting ledger on the FULL raw sheets vs the raw pre-enrichment
    # records (see core/line_ledger). Read-only; must precede pack-strip below.
    from core.line_ledger import audit_sheet_rows
    try:
        line_audit = audit_sheet_rows(sheets, records)
    except Exception:  # ledger must never break extraction
        line_audit = {"applicable": False, "reason": "ledger error"}

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
    # ---- sanity-directed dispatch fallback (see module docstring block above). ----
    # Only a mostly-failing generic-tabular read is reconsidered; never re-entered
    # (forced_layout is set on the retry) and never triggered for gated layouts, so
    # every file that parses acceptably today is byte-identical.
    if (forced_layout is None and layout == "tabular" and sheets_ref
            and sanity.get("checked", 0) >= _FALLBACK_MIN_CHECKED
            and sanity.get("pass_rate", 1.0) <= _FALLBACK_TRIGGER_PASS_RATE):
        for _cand, _gate in SANITY_FALLBACKS:
            try:
                if not _gate(sheets_ref):
                    continue
                alt = extract(file_bytes, {**settings, "_forced_layout": _cand})
            except Exception:
                continue  # a broken candidate must never take down the good path
            alt_sanity = alt.get("sanity") or {}
            if (alt_sanity.get("checked", 0) >= _FALLBACK_MIN_CHECKED
                    and alt_sanity.get("pass_rate", 0.0) >= _FALLBACK_ACCEPT_PASS_RATE
                    and len(alt.get("rows", [])) >= _FALLBACK_MIN_ROW_RATIO * max(len(records), 1)):
                alt.setdefault("warnings", []).append(
                    f"sanity-fallback: tabular pass_rate "
                    f"{sanity.get('pass_rate', 0.0):.0%} -> {_cand} "
                    f"{alt_sanity.get('pass_rate', 0.0):.0%}"
                )
                return alt
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
        "line_audit": line_audit,
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
        "debug": {
            "parser": "stock_xlsx",
            "layout": layout,
            "layout_label": LAYOUT_LABELS.get(layout, layout),
            "sheet": sheet_name,
            "row_count": len(records),
        },
    }
