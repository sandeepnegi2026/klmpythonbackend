import pandas as pd

from core.canonical import numeric_fields


# A bare dash printed in a numeric column ("-", en/em dash) means "nil" in these pharma
# exports (most commonly the FREE column when a line has no free goods). ``to_numeric``
# coerces it to NaN, so without this it survived as the literal "-" string. Converting only
# a lone dash to 0 never touches a real number or a genuinely blank cell.
_DASH_NIL = {"-", "–", "—"}


def cast_numbers(records):
    for field in numeric_fields("party"):
        raw = [row.get(field, "") for row in records]
        values = pd.to_numeric(pd.Series(raw), errors="coerce")
        for row, orig, value in zip(records, raw, values):
            if pd.notna(value):
                row[field] = float(value)
            elif str(orig).strip() in _DASH_NIL:
                row[field] = 0.0
