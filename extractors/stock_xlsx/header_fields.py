import re

from core.header_match import match_header

from core.canonical import DIVISIONS


def detect_header_row(rows, hint=None):
    if hint:
        idx = max(0, int(hint) - 1)
        return idx if idx < len(rows) else None
    for idx, row in enumerate(rows[:150]):
        matched_keys = {match_header(cell, "stock")[0] for cell in row}
        matched_keys.discard(None)
        if len(matched_keys) >= 4:
            return idx
    return None


def _strip_html(s):
    """Strip HTML tags and entities from a string."""
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"&\w+;", " ", s)
    return s.strip()


def extract_header_fields(rows):
    fields = {}
    flat = "\n".join(" ".join(row) for row in rows[:12])
    lines = [line.strip() for line in flat.splitlines() if line.strip()]

    # Detect the header row so we can skip it when looking for vendor name
    header_idx = detect_header_row(rows)

    if rows:
        first = next(
            (
                _strip_html(cell)
                for row_idx, row in enumerate(rows[:5])
                for cell in row
                if cell
                and _strip_html(cell)
                and "stock" not in cell.lower()
                and "sale" not in cell.lower()
                and "statement" not in cell.lower()
                and not re.match(r"^\s*<[^>]+>\s*$", cell)
                and (header_idx is None or row_idx != header_idx)
                and not match_header(cell, "stock")[0]
            ),
            "",
        )
        if first:
            fields["vendor_name"] = first
    # Report period comes from the upload-time month selection, not the document.
    upper = flat.upper()
    for div in DIVISIONS:
        if div in upper:
            fields["division"] = div
            break
    title = next((line for line in lines[:8] if "stock" in line.lower()), "")
    if title:
        fields["report_type_label"] = title
    return fields


def header_detected_from_fields(fields):
    return {f"header.{key}": key for key, value in fields.items() if value}
