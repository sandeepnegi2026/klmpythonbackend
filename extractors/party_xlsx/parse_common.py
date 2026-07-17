import re

import pandas as pd

from core.header_match import normalize

from extractors.party_xlsx.constants import SUBTOTAL_RE


def compact(value):
    return normalize(value).replace(" ", "")


def cell_text(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


def split_party_area(raw_party):
    raw = raw_party.strip()
    if not raw:
        return "", ""
    if "," in raw:
        parts = [part.strip() for part in raw.split(",")]
        return parts[0], parts[-1]
    if "-" in raw:
        idx = raw.rfind("-")
        left, right = raw[:idx].strip(), raw[idx + 1 :].strip()
        if right and len(right) <= 30:
            return left, right
    return raw, ""


def is_subtotal(text):
    return bool(text and SUBTOTAL_RE.search(text))


def is_numeric_qty(value):
    if not str(value).strip():
        return False
    parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return pd.notna(parsed)


def looks_like_date(value):
    text = cell_text(value)
    if not text:
        return False
    return bool(
        re.match(r"^\d{4}-\d{2}-\d{2}", text)
        or re.match(r"^\d{2}-\d{2}-\d{2}", text)
        or re.match(r"^\d{2}/\d{2}/\d{4}", text)
    )


def row_dict(headers, raw_row):
    record = {}
    for idx, header in enumerate(headers):
        record[str(header)] = raw_row[idx] if idx < len(raw_row) else ""
    return record


def label_value(raw_row, label_prefix):
    for idx, cell in enumerate(raw_row):
        text = cell_text(cell).lower().rstrip(" :")
        if text.startswith(label_prefix):
            for j in range(idx + 1, len(raw_row)):
                val = cell_text(raw_row[j])
                if val and not cell_text(raw_row[j]).lower().startswith(label_prefix):
                    return val
    return ""
