import io
import json
import pandas as pd

from core.canonical import CANONICAL_FIELDS

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


def build_csv(rows, report_type=None):
    return rows_to_dataframe(rows, report_type).to_csv(index=False).encode("utf-8")


def build_xlsx(rows, report_type=None):
    buffer = io.BytesIO()
    rows_to_dataframe(rows, report_type).to_excel(buffer, index=False, engine="openpyxl")
    return buffer.getvalue()


def build_json(payload):
    return json.dumps(payload, indent=2, default=str).encode("utf-8")
