# Pharma Report Extractor Spike

Streamlit spike for extracting two pharma distributor report families through four isolated routes. `app.py` only handles UI, settings, routing, coverage, downloads, and scoring; extraction logic lives in one module per report type and file format.

## How to run

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Routes

| Report | Format | Package |
|---|---|---|
| Party-wise Sales | PDF | `extractors/party_pdf/` |
| Party-wise Sales | Excel `.xlsx` / `.xls` | `extractors/party_xlsx/` |
| Stock & Sales Report | PDF | `extractors/stock_pdf/` |
| Stock & Sales Report | Excel `.xlsx` / `.xls` | `extractors/stock_xlsx/` |

Layout keys use **ERP/software names** (e.g. `busy_tally`, `infosoft_bandwise`), not distributor names. See [AGENTS.md](AGENTS.md) for the full layout catalog.

## Stock & Sales

The stock lane extracts one row per product per period and maps movement columns to canonical fields such as `opening_stock`, `purchase_stock`, `purchase_free`, `purchase_return`, `sales_qty`, `sales_value`, `sales_free`, `sales_return`, `closing_stock`, and `closing_stock_value`.

PDF extraction defaults to ruled-table/lattice parsing and falls back to text-line parsing for vendor reports that render as plain stock statements. Excel extraction unmerges title/header cells, auto-picks the sheet with stock headers, maps columns by synonyms, drops subtotal rows, and runs the shared stock sanity equation.

The sanity check is:

```text
opening_stock + purchase_stock - purchase_return - sales_qty - sales_return ~= closing_stock
```

Warnings are shown in the `Sanity Warnings` tab and included in the JSON dump.

## Shared contract

Every extractor returns:

```python
{
    "rows": [{"canonical_key": "value"}],
    "headers_detected": {"source_header": "canonical_key"},
    "pages": [{"page_no": 1, "char_count": 0, "line_count": 0, "rect_count": 0, "table_bboxes": []}],
    "raw_text": "...",
    "warnings": [],
    "elapsed_ms": 0,
}
```

## Test protocol

Run each of the 12 vendor files through the matching route. For every file, screenshot the Coverage and Score tabs, paste the score into a results table, and then decide go/no-go on the Python migration.

## Regression tests

Before changing any extractor or parser, read **[AGENTS.md](AGENTS.md)** — it documents architecture, risk areas, and the mandatory workflow for AI agents and developers.

```bash
# Run committed baselines (Party CG PDF — 39 files)
python scripts/regression_test.py --suite party_cg_pdf

# Stock & Sales baselines (Sales Diff folder — 24 PDF + 10 Excel)
python scripts/regression_test.py --suite stock_pdf --suite stock_xlsx

# List all configured suites
python scripts/regression_test.py --list-suites

# Refresh baselines after an intentional parser improvement
python scripts/regression_test.py --suite party_cg_pdf --update
```

Baselines live in `tests/baselines/`. Test data paths are configured in `tests/regression_manifest.json` (expects `Reports/Party Wise/...` next to this repo).
