import io
import json
import pandas as pd

from core.canonical import CANONICAL_FIELDS, numeric_fields

# Columns that must never surface in the UI or exports.
#   raw_division                 — internal pre-enrichment value
#   report_start_date/_end_date  — owned by the upload-time month selection,
#                                  not extraction; never shown or exported here
HIDDEN_COLUMNS = ["raw_division", "report_start_date", "report_end_date"]

# Preferred leading column order for preview/exports, per report type. Listed
# fields are surfaced first, in this exact order; any remaining canonical fields
# follow in their canonical.py order, then non-canonical extras. Display-only —
# does not touch extraction, header matching, or scoring.
PARTY_OUTPUT_ORDER = [
    "vendor_name", "division", "party_name", "party_location",
    "product_name", "pack", "qty", "free_qty", "rate", "amount", "taxable_value",
]
# Stock & Sales required data fields first, matching the demo layout:
# PRODUCT NAME | PACK | OPENING STOCK | PURCHASE STOCK | PURCHASE FREE |
# PURCHASE RETURN | SALES QTY | SALES VALUE | SALES FREE | SALES RETURN |
# CLOSING STOCK | CLOSING STOCK VALUE.
STOCK_OUTPUT_ORDER = [
    "product_name", "pack",
    "opening_stock", "purchase_stock", "purchase_free", "purchase_return",
    "sales_qty", "sales_value", "sales_free", "sales_return",
    "closing_stock", "closing_stock_value",
]
OUTPUT_ORDER = {"party": PARTY_OUTPUT_ORDER, "stock": STOCK_OUTPUT_ORDER}

# Numeric fields that are per-unit RATES or PERCENTAGES — summing them down a
# column is meaningless (a total of 232 products' MRPs, or of their GST%, is not a
# number anyone wants). The export TOTAL row sums every OTHER numeric column
# (quantities + money values) and leaves these blank.
RATE_LIKE_FIELDS = {"mrp", "rate", "ptr", "purchase_rate", "gst_rate", "discount_percent"}


def _additive_fields(report_type):
    """Numeric canonical fields that are meaningful to sum (excludes rates/percents)."""
    if not report_type or report_type not in CANONICAL_FIELDS:
        return []
    return [f for f in numeric_fields(report_type) if f not in RATE_LIKE_FIELDS]


def rows_to_dataframe(rows, report_type=None):
    df = pd.DataFrame(rows or [])
    if report_type and not df.empty and report_type in CANONICAL_FIELDS:
        canonical_keys = list(CANONICAL_FIELDS[report_type].keys())
        lead_order = OUTPUT_ORDER.get(report_type)
        if lead_order:
            lead = [k for k in lead_order if k in canonical_keys]
            canonical_keys = lead + [k for k in canonical_keys if k not in lead]
        ordered_cols = [k for k in canonical_keys if k in df.columns]
        extra_cols = [k for k in df.columns if k not in ordered_cols]
        df = df[ordered_cols + extra_cols]

    drop_cols = [c for c in HIDDEN_COLUMNS if c in df.columns]
    if drop_cols:
        df = df.drop(columns=drop_cols)

    return df


def _to_number(value):
    """Parse an export cell to float; None for blank/"-"/unparseable.

    Mirrors core.triage._to_float but kept local so this low-level export module
    stays decoupled from the analytics layer (avoids an import cycle risk)."""
    if value is None:
        return None
    text = str(value).replace(",", "").strip()
    if text in ("", "-"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _distinct_count(series):
    """Count of distinct non-empty values (trimmed, case-insensitive)."""
    seen = set()
    for value in series:
        if value is None:
            continue
        text = str(value).strip().lower()
        if text:
            seen.add(text)
    return len(seen)


def _fmt_total(series):
    """Sum a column's parseable cells → display string. Integer-valued sums lose
    the decimals (23507), fractional sums keep two places (34,52,881.65 → 3452881.65)."""
    total, seen = 0.0, False
    for value in series:
        number = _to_number(value)
        if number is not None:
            total += number
            seen = True
    if not seen:
        return "0"
    total = round(total, 2)
    if total == int(total):
        return str(int(total))
    return f"{total:.2f}"


def append_totals_row(df, report_type=None):
    """Return `df` with one grand-total row appended (download-only).

    Sums the additive numeric columns (quantities + money values); per-unit rate
    and percentage columns stay blank. The first column carries the "TOTAL" label;
    the party/product name columns carry the distinct party/product counts. When a
    name column IS the first (label) column — stock's product_name — the label wins
    and the count moves to the next column so "TOTAL" is never clobbered."""
    if df is None or df.empty:
        return df

    columns = list(df.columns)
    label_col = columns[0]
    total_row = {col: "" for col in columns}
    total_row[label_col] = "TOTAL"

    additive = set(_additive_fields(report_type))
    for col in columns:
        if col in additive:
            total_row[col] = _fmt_total(df[col])

    if "party_name" in columns and "party_name" != label_col:
        total_row["party_name"] = f"{_distinct_count(df['party_name'])} parties"
    if "product_name" in columns:
        product_count = _distinct_count(df["product_name"])
        if "product_name" != label_col:
            total_row["product_name"] = f"{product_count} products"
        elif len(columns) > 1:
            total_row[columns[1]] = f"{product_count} products"

    totals_df = pd.DataFrame([total_row], columns=columns)
    return pd.concat([df, totals_df], ignore_index=True)


def build_csv(rows, report_type=None):
    df = append_totals_row(rows_to_dataframe(rows, report_type), report_type)
    return df.to_csv(index=False).encode("utf-8")


def build_xlsx(rows, report_type=None):
    buffer = io.BytesIO()
    df = append_totals_row(rows_to_dataframe(rows, report_type), report_type)
    df.to_excel(buffer, index=False, engine="openpyxl")
    return buffer.getvalue()


def build_json(payload):
    return json.dumps(payload, indent=2, default=str).encode("utf-8")
