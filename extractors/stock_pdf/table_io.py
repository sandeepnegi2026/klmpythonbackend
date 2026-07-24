import io
import re

import pdfplumber

from core.header_match import map_headers, match_header

from extractors.stock_pdf.constants import SUBTOTAL_RE
from extractors.stock_pdf.parse_common import _clean, _is_num


def _table_settings(strategy="lattice", settings=None):
    settings = settings or {}
    v = h = "lines" if strategy != "stream" else "text"
    return {
        "vertical_strategy": v,
        "horizontal_strategy": h,
        "snap_tolerance": float(settings.get("snap_tolerance", 3)),
        "join_tolerance": float(settings.get("join_tolerance", 3)),
        "intersection_tolerance": float(settings.get("intersection_tolerance", 3)),
        "text_x_tolerance": float(settings.get("x_tolerance", 3)),
        "text_y_tolerance": float(settings.get("y_tolerance", 3)),
    }


def _merge_multiline_product(rows):
    """Handle Marg web stock format where product names span multiple lines."""
    merged = []
    buffer_name = ""
    buffer_nums = None
    for row in rows:
        cells = [_clean(c) for c in row]
        has_nums = sum(1 for c in cells[1:] if c and _is_num(c)) >= 3
        if has_nums:
            if buffer_name and buffer_nums is None:
                cells[0] = buffer_name + " " + cells[0]
            merged.append(cells)
            buffer_name = ""
            buffer_nums = None
        elif cells[0] and not has_nums:
            if buffer_name:
                buffer_name += " " + cells[0]
            else:
                buffer_name = cells[0]
    return merged


def _header_score(row):
    """Score a row as a potential header row."""
    text = " ".join(_clean(c) for c in row)
    score = sum(1 for c in row if match_header(_clean(c), "stock")[0])
    score += len(
        re.findall(
            r"open|sale|closing|purchase|receipt|issue|product", text, re.I
        )
    )
    return score


def _merge_split_tables(tables):
    """Merge header-only table with adjacent data-only table.

    Some Marg bordered PDFs produce separate pdfplumber tables for the
    header band and the data band.  Detect this and stitch them together.
    """
    merged = []
    i = 0
    while i < len(tables):
        tbl = tables[i]
        # Check if this is a header-only table (<=3 rows, has a good header)
        if tbl and 1 <= len(tbl) <= 3:
            best_score = max((_header_score(row) for row in tbl), default=0)
            if best_score >= 2 and i + 1 < len(tables):
                next_tbl = tables[i + 1]
                # Next table has data but no good header row?
                if next_tbl and len(next_tbl) >= 1:
                    next_best = max(
                        (_header_score(row) for row in next_tbl[:5]), default=0
                    )
                    if next_best < 2:
                        # Stitch: append header rows + data rows
                        merged.append(tbl + next_tbl)
                        i += 2
                        continue
        merged.append(tbl)
        i += 1
    return merged


def _rows_from_data(data_rows, headers, detected, layout_hint=""):
    """Map data rows onto an already-identified header/detected pair.

    Shared by the primary (header-bearing) table and the header-carry path for
    headerless CONTINUATION tables, so division-2+ blocks that repeat no column
    header are no longer silently dropped whole.
    """
    if layout_hint == "marg_web_stock":
        data_rows = _merge_multiline_product(data_rows)
    records = []
    for raw_row in data_rows:
        values = [_clean(c) for c in raw_row]
        record = {}
        for idx, header in enumerate(headers):
            key = detected.get(header)
            if key and idx < len(values):
                record[key] = values[idx]
        product = _clean(record.get("product_name"))
        if not product or SUBTOTAL_RE.match(product):
            continue
        records.append(record)
    return records


def _records_from_table(table, layout_hint=""):
    """Extract records from a pdfplumber table.

    Returns ``(records, detected, headers)``. ``headers`` is None when no header
    row is found (score < 2), so a caller can carry a prior table's header
    forward onto this headerless continuation block instead of dropping it.
    """
    if not table or len(table) < 2:
        return [], {}, None
    best_idx, best_score = None, 0
    for idx, row in enumerate(table[:8]):
        score = _header_score(row)
        if score > best_score:
            best_idx, best_score = idx, score
    if best_idx is None or best_score < 2:
        return [], {}, None

    headers = [_clean(c) or f"col_{i}" for i, c in enumerate(table[best_idx])]
    header_map = map_headers(headers, "stock")
    detected = {raw: info["canonical"] for raw, info in header_map.items()}

    if "product_name" not in set(v for v in detected.values() if v):
        return [], detected, None

    records = _rows_from_data(table[best_idx + 1 :], headers, detected, layout_hint)
    return records, detected, headers


def parse_bordered(pdf_bytes, settings, layout_hint=""):
    """Parse PDFs with rectangular bordered tables."""
    rows = []
    detected = {}
    last_headers = None
    last_detected = None
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            for strategy in ["lattice", "stream"]:
                ts = _table_settings(strategy, settings)
                tables = page.extract_tables(ts) or []
                tables = _merge_split_tables(tables)
                for table in tables:
                    r, d, hdrs = _records_from_table(table, layout_hint)
                    if r:
                        rows.extend(r)
                        detected.update(d)
                        last_headers, last_detected = hdrs, d
                    elif last_headers and table and len(table) >= 1:
                        # Headerless CONTINUATION table: a division-2+ block whose
                        # column header is printed only once (top of the report), so
                        # pdfplumber emits it as its own header-less table that used
                        # to be dropped whole. Re-map its rows onto the last real
                        # header when the column count lines up (subtotal/band rows
                        # are still filtered by _rows_from_data's product-name gate).
                        width = max((len(row) for row in table), default=0)
                        if width and abs(width - len(last_headers)) <= 1:
                            r2 = _rows_from_data(table, last_headers,
                                                 last_detected, layout_hint)
                            if r2:
                                rows.extend(r2)
                                detected.update(last_detected)
                if rows:
                    break
    return rows, detected
