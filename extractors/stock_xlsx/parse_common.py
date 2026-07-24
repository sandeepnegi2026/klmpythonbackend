import pandas as pd

from extractors.stock_xlsx.constants import SUBTOTAL_RE


def cell_text(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


def to_number(value):
    text = cell_text(value).replace(",", "")
    if text in {"", "-", "-----"}:
        return 0.0
    text = text.rstrip(".")
    parsed = pd.to_numeric(pd.Series([text]), errors="coerce").iloc[0]
    return float(parsed) if pd.notna(parsed) else None


def split_plus_qty(value):
    text = cell_text(value)
    if "+" in text:
        left, right = text.split("+", 1)
        return to_number(left) or 0.0, to_number(right) or 0.0
    return to_number(text) or 0.0, 0.0


def is_subtotal(text):
    return bool(text and SUBTOTAL_RE.match(text))
