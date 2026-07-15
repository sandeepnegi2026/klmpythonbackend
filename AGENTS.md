# Agent & Developer Guide — Pharma Report Extractor

**Read this entire document before changing any extractor, parser, or shared helper code.**

This project parses real vendor PDF/Excel reports from pharmaceutical distributors. A small change in one regex or detection rule can silently break dozens of already-working files. The regression suite exists to catch that.

---

## 0. Two copies of this engine — which one ships (READ FIRST)

The extractor engine (`core/` + `extractors/`) is duplicated in two sibling folders:

| Folder | Role | Deployed to server? |
|---|---|---|
| **`Backends/`** (`pdf-spike-service`) | FastAPI service: `main.py` → `pdf_spike.py` → `extractors/` + `core/` | ✅ **YES — this is what runs in production** (Render / Docker) |
| **`Python-Service-UI/`** (`pdf-spike`) | Streamlit test harness (`app.py`) + triage tooling (`scripts/triage_batch.py`, `NEW_BATCH_RUNBOOK.md`, `tests/test_triage.py`) | ❌ No — **testing / triage only** |

**RULE: every change to a parser, `detect_*`, `registry`, a layout module, or any `core/` file MUST be applied to `Backends/`.** Production serves `Backends/` only — a fix that lands solely in `Python-Service-UI/` is tested-green but **never ships**. `Python-Service-UI/` is the sandbox (triage a batch, preview in Streamlit, run unit tests); `Backends/` is the deliverable.

**Workflow for any extraction change:**
1. Develop & test in `Python-Service-UI/` (triage, `app.py`, `python tests/test_triage.py`).
2. **Apply the identical change to `Backends/`** (the edited `core/` / `extractors/` files).
3. Verify the two engines match before you finish — run from the `Projects/` root:
   ```bash
   diff -rq Backends/core       Python-Service-UI/core
   diff -rq Backends/extractors Python-Service-UI/extractors
   # ignore __pycache__; expect NO differences. Any diff = drift → reconcile before deploy.
   ```
4. Re-run the regression suite (§10) on `Backends/` before deploying.

### 0.1 A green test in `Python-Service-UI/` does NOT prove `Backends/` will run

Mirroring the code is necessary but **not sufficient**. The two folders are byte-identical **only** in `core/` + `extractors/` — everything around the engine differs, and those differences are exactly what break a live deploy. A passing PSUI test never exercises them.

- **Extraction _results_ transfer for free.** Byte-identical code + same input file = identical rows/totals (deterministic). You do **not** need to re-verify per-file extraction correctness on `Backends/` — a file that extracts right in PSUI extracts right in `Backends/`.
- **The _runtime_ does NOT transfer.** PSUI runs locally (Windows, your installed packages, Streamlit `app.py`). `Backends/` runs in a **Linux Docker container** that does a fresh `pip install -r Backends/requirements.txt` and serves via **FastAPI `main.py` → `pdf_spike.py`**. A PSUI test touches none of that.

What a green PSUI run silently misses — each fails **only** on `Backends/`:

| Gap | How it bites in production | Cheap guard |
|---|---|---|
| New `import` not added to **`Backends/requirements.txt`** | container lacks the package → `uvicorn main:app` boots into `ModuleNotFoundError` → **whole service down** | `cd Backends && python -c "import main"` |
| Changed `extract()` output contract / canonical key | `app.py` copes but `pdf_spike.py` reads the old shape → HTTP returns empty/wrong; PSUI never ran this path | one real `/extract` call |
| Case-sensitive import or path (`import Constants` vs `constants.py`) | fine on Windows/PSUI, `ModuleNotFoundError` on the Linux container | Docker build |
| New `data/*` asset a layout loads, `.py` mirrored but file not | works from `PSUI/data/`, missing under `Backends/` at runtime | import smoke + `/extract` |

**The failure mode is usually a TOTAL outage** (container won't start) — not a graceful per-file miss.

**RULE: after mirroring, never deploy on the strength of a PSUI-only test — run at minimum a boot smoke test on `Backends/`.**

```bash
cd Backends && python -c "import main"     # all engine + service imports resolve in the deploy tree
# gold standard — validate the actual shipping artifact:
docker build -t be . && docker run -p 8000:8000 be
#   then hit /healthz and one real /extract
```

When adding a new layout, also confirm before deploy: (a) any new third-party dependency is in `Backends/requirements.txt`, and (b) any new `data/` asset exists under `Backends/`.

---

## 1. Mandatory workflow (every change)

1. **Identify the route** — Party PDF, Party Excel, Stock PDF, or Stock Excel (`app.py` routes by report type × file format).
2. **Identify the format/layout** — e.g. `busy_tally`, `marg_register`. This is **not** the vendor name (AYACHI, RACHIT, BASTAR can all share one format).
3. **Decide the scenario** (see §4.1) — new layout vs new vendor on an existing layout.
4. **Prefer the smallest safe change** — extend the shared parser for that format; do not create one parser per vendor.
5. **Run regression tests before and after**:
   ```bash
   python scripts/regression_test.py --suite party_cg_pdf
   ```
6. **If metrics change intentionally**, update baselines and explain why:
   ```bash
   python scripts/regression_test.py --suite party_cg_pdf --update
   ```
7. **Never “fix one file” by breaking detection for others** — re-test the whole affected suite.

**Exception — presentation-only changes skip regression (still mirror them).** The suite snapshots metrics computed from the extracted **row dicts** (`row_count`, `product_count`, totals, `detected_format`) and never touches the display/export layer — it doesn't call `rows_to_dataframe`, `build_csv`, or `build_xlsx`. So a change that only affects how already-extracted rows are *presented* — column order/labels in `core/io_helpers.py`, download formatting — cannot move any baseline, and steps 5–6 add no signal. Such a change **must still be mirrored to `Backends/`** (production serves `Backends/`; keep the two trees byte-identical), but a regression run is not required. If unsure whether a change is truly presentation-only (i.e. it might alter which rows/values are produced), run the suite — it's cheap insurance.

---

## 2. Architecture overview

```
app.py                          UI only — routing, tabs, downloads, score display
├── extractors/
│   ├── party_pdf/              Party-wise Sales PDF (package)
│   │   ├── pipeline.py         extract() orchestration
│   │   ├── detect.py             detect_format()
│   │   ├── registry.py         PARSERS dict
│   │   └── layouts/              one module per ERP/layout
│   ├── party_xlsx/             Party-wise Sales Excel (package)
│   ├── stock_pdf/              Stock & Sales PDF (package)
│   └── stock_xlsx/             Stock & Sales Excel (package)
└── core/
    ├── canonical.py            Field definitions (PARTY_FIELDS, STOCK_FIELDS)
    ├── header_match.py         Fuzzy header → canonical mapping
    ├── scoring.py              Coverage + quality score
    └── io_helpers.py           CSV / JSON / XLSX export
```

Each route is a **package** with `pipeline.py` (public `extract()`), `detect.py`, `registry.py`, and `layouts/` — not a single monolith file.

### Extraction pipeline (Party PDF example)

```
PDF bytes
  → pdf_io.read + _decode_cid()     (only if text contains "(cid:...)")
  → detect_format()                 picks ONE layout key (ERP/software name)
  → PARSERS[format]()               runs ONE layout parser
  → extract_party_and_area()        format-specific name/area split
  → _canonicalize_rows()            maps to canonical field keys
  → extract() contract output       rows, headers_detected, warnings, debug, ...
```

Each route is **isolated**. UI and scoring do not need changes when adding a parser — as long as the output contract is preserved.

### Naming rule (critical)

Layout keys and parser files are named after **ERP / software export structure**, never after distributor (client) names:

| Wrong (client) | Right (software/layout) |
|---|---|
| `parse_tirupati`, `parse_ganesh` | `parse_marg_sale_details`, `parse_infosoft_bandwise` |
| `ahuja_long`, `bhawani` | `marg_stock_long`, `stock_simple_7col` |
| `detected_format: ganesh` | `detected_format: infosoft_bandwise` |

Human-readable labels live in each package's `constants.py` → `LAYOUT_LABELS` / `FORMAT_LABELS`.

---

## 3. Output contract (do not break)

Every extractor must return:

```python
{
    "rows": [{"canonical_key": "value", ...}],
    "headers_detected": {"source_header": "canonical_key"},
    "pages": [{"page_no": 1, "char_count": 0, ...}],
    "raw_text": "...",
    "warnings": [],
    "elapsed_ms": 0,
}
```

Party canonical keys include: `party_name`, `party_area`, `product_name`, `qty`, `free_qty`, `rate`, `amount`, …

Stock canonical keys include: `product_name`, `opening_stock`, `purchase_stock`, `sales_qty`, `closing_stock`, …

**Do not rename these keys** without updating `core/canonical.py`, `core/scoring.py`, and all baselines.

---

## 4. Risk matrix — what can break existing PDFs

| Change location | Risk | Affects |
|---|---|---|
| New `parse_*()` + new `PARSERS` entry + specific `detect_format` rule | **Low** | Only files matching the new rule |
| Edit `detect_format()` order or broaden a rule | **High** | Can mis-route many files to wrong parser |
| Edit an existing `parse_*()` function | **Medium–High** | All files using that format (e.g. all `busy_tally`) |
| Edit `extract_party_and_area(..., fmt)` for one `fmt` | **Medium** | All files of that format |
| Edit `_decode_cid()` | **Medium** | All PDFs with CID glyphs (safe if gated on `(cid:` presence) |
| Edit `core/header_match.py` or `canonical.py` | **High** | All routes |
| Edit `app.py` UI only | **Low** | Display only |

### Rule of thumb

Use **format/layout** as the unit of code — not vendor name.

| Scenario | What to do | Do **not** do |
|---|---|---|
| **New layout** (structure not seen before) | Add new `parse_*()` + new `detect_format` rule + `PARSERS` entry | Reuse the wrong parser because the report “looks similar” |
| **New vendor, same layout** (already detected as e.g. `busy_tally`) | **Reuse existing parser** — extend it if the vendor has a minor quirk | Create `parse_rachit()`, `parse_new_vendor()`, or vendor-specific detect rules |
| **Same layout, one vendor quirk** | Extend the **shared** parser for that format (or shared helper like `_decode_cid`) | Hardcode `if "RACHIT" in text` in shared logic |
| **Never** | — | Add vague detect rules like `"party" in text` — they steal files from other parsers |

### 4.1 Vendor vs format — critical distinction

- **Vendor** = distributor name on the letterhead (AYACHI MEDICAL, RACHIT MEDICAL, BASTAR PHARMA, TIRUPATI MEDICOSE, …).
- **Format / layout** = ERP export structure (Busy/Tally party-wise summary, Marg register, Logic ERP, …).

**Many vendors → one format.** That is normal and intentional.

Example — all of these CG Party PDFs use the **`busy_tally`** format:

| Vendor | Party line style | Same parser? |
|---|---|---|
| AYACHI MEDICAL | `PARTY NAME-AREA` (hyphen) | Yes — `parse_busy_tally()` |
| RACHIT MEDICAL | `PARTY NAME` or `PARTY NAME AREA` (no hyphen) | Yes — same parser, extended party/area logic |
| BASTAR PHARMA | Busy/Tally “Party / Item Wise” layout | Yes |
| TIRUPATI MEDICOSE | Same header band, same column layout | Yes |

When a **new vendor** uploads a file:

1. Extract raw text and run `detect_format()` (or check `detected_format` in the UI).
2. If it matches an existing format key → **no new parser**. Fix only if that vendor exposes a gap in the shared parser; regression-test **all vendors** on that format.
3. If it returns `unknown` or clearly different columns/headers → **new layout** → add a new parser (§6).

**Naming rule:** parsers are named after **layout** (`parse_busy_tally`, `parse_marg_register`), never after a vendor (`parse_rachit` is wrong).

---

## 5. Party PDF — formats and parsers

Package: `extractors/party_pdf/` — see `constants.py` → `FORMAT_LABELS` for display names.

| Format key | Software / ERP | Parser module | Typical signals |
|---|---|---|---|
| `marg_summary` | Marg ERP | `layouts/marg_summary.py` | Sales Detail Summary, MF-Customer |
| `marg_register` | Marg ERP | `layouts/marg_register.py` | Sales Detail Register |
| `marg_register_itemwise` | Marg / Pharmabyte | `layouts/marg_register_itemwise.py` | Itemwise-Customerwise register |
| `marg_sale_details` | Marg ERP | `layouts/marg_sale_details.py` | “Sale Details” + ruled lines |
| `marg_bordered` | Marg ERP | `layouts/marg_bordered.py` | Bordered tables, `from: DD/MM` |
| `marg_bordered_billwise` | Neosoft / Marg | `layouts/marg_bordered_billwise.py` | Bordered + “Bill No” |
| `unisolve` | Unisolve | `layouts/unisolve.py` | Customer-wise Product-wise |
| `busy_tally` | Busy/Tally | `layouts/busy_tally.py` | “Party / Item Wise” |
| `busy_tally_itemwise` | Busy/Tally / Marg | `layouts/busy_tally.py` | “Item / Item Wise” |
| `logic_erp` | Logic ERP | `layouts/logic_erp.py` | Customer / Company / Itemwise |
| `wep_legacy` | GoFrugal / WEP | `layouts/wep_legacy.py` | “Product C” + `====` |
| `prompt_normal` | Prompt ERP | `layouts/prompt.py` | Normal From + Bill Ref |
| `prompt_free_qty` | Prompt ERP | `layouts/prompt.py` | Free Quantity + Bill Ref |
| `technomax_free_qty` | Technomax | `layouts/technomax.py` | Free Quantity Statement |
| `custom_pharma` | Prompt ERP variant | `layouts/custom_pharma.py` | DB-T/ bill refs |

`detect_format()` runs **top to bottom** — first match wins. New rules must be **more specific** and inserted **above** broader rules.

---

## 6. How to add support for a **new layout** (not a new vendor)

Use this section only when `detect_format()` returns `unknown` or the file’s **structure** (headers, columns, party banding) does not match any existing format.

**If the new file already detects as `busy_tally`, `marg_register`, etc.** → skip this section; go to §7 (extend the shared parser).

1. Inspect raw text (Streamlit “Raw Text” tab or `party_pdf.extract_pdf(bytes)`).
2. Confirm no existing format matches — check `detected_format` in debug output.
3. Add `parse_<layout_name>(text)` returning `(headers, rows)` — name after **layout**, not vendor.
4. Add a **specific** rule to `detect_format()` **before** generic fallbacks.
5. Register in `PARSERS` dict and `FORMAT_LABELS`.
6. If party/area splitting is unique to this layout, add a branch in `extract_party_and_area(raw, "<layout_name>")`.
7. Run regression on all suites; add a baseline for the new file:
   ```bash
   python scripts/regression_test.py --suite party_cg_pdf --update
   ```

### Template (new layout only)

```python
def parse_some_erp_layout(text):  # layout name, not vendor name
    H = ['Party Name', 'Area', 'Product Name', 'Qty', 'Rate', 'Amount']
    rows = []
    # ... line-by-line parsing ...
    return H, rows

PARSERS = {
    ...
    "some_erp_layout": parse_some_erp_layout,
}
```

---

## 7. New vendor on an **existing** format (most common case)

When a new distributor uploads a file but it uses a layout you already support:

1. Confirm `detected_format` matches the expected key (e.g. both AYACHI and RACHIT → `busy_tally`).
2. **Do not** add a new parser or vendor-specific detect rule.
3. If extraction fails or is incomplete, extend the **shared** parser or helper for that format so **all vendors** on that layout keep working.

Example: RACHIT and AYACHI both use `busy_tally`.

| Issue | Fix location | Regression scope |
|---|---|---|
| `(cid:53)` glyphs instead of text | `_decode_cid()` in `extractors/party_pdf/pdf_io.py` | All CID-encoded PDFs (any vendor) |
| Party lines without `-AREA` suffix | `parse_busy_tally()` party heading regex | **All** `busy_tally` PDFs |
| Area embedded after STORE/PHARMACY suffix | `extract_party_and_area(..., "busy_tally")` | **All** `busy_tally` without hyphen |

**Always re-test every vendor on that format** — e.g. when fixing RACHIT, re-test AYACHI, BASTAR, JINDAL, etc., because they all share `parse_busy_tally()`.

Steps:

1. Decode/extract text first — confirm the problem is parsing, not text extraction.
2. Change only the relevant **format-level** parser or `extract_party_and_area` branch.
3. Run `python scripts/regression_test.py --suite party_cg_pdf`.
4. If row counts, party counts, area counts, or totals change for **any** file on that format → **stop and investigate**.

### Checklist: new vendor upload

- [ ] `detected_format` is an existing key → reuse parser, no new `PARSERS` entry
- [ ] Rows extract correctly → add baseline only: `--update`
- [ ] Rows wrong/missing → extend shared parser; regression-test **all** files with same `detected_format`
- [ ] `detected_format` is `unknown` → new layout (§6)

---

## 8. Known PDF extraction limitations

| Symptom | Cause | Approach |
|---|---|---|
| `(cid:NN)` in raw text | Font encoding without Unicode cmap | `_decode_cid()` with offset +29 (already implemented) |
| Empty raw text, zero chars | Scanned/image PDF | OCR required — parser cannot help |
| Wrong format detected | Overly broad `detect_format` rule | Narrow the rule; add regression baseline |

Do not assume “zero rows = parser bug” — check `raw_text` and `char_count` first.

---

## 9. Stock extractors

Packages: `extractors/stock_pdf/`, `extractors/stock_xlsx/` — layout keys in `detect.py`, parsers in `layouts/`.

### Stock PDF layouts

| Layout key | Software / structure | Module |
|---|---|---|
| `simple4` | Busy/Tally Simple4 | `layouts/simple4.py` |
| `value_pairs` | Marg qty+value pairs | `layouts/value_pairs.py` |
| `marg_stock_long` | Marg long movements | `layouts/marg_stock_long.py` |
| `marg_qty_value_wide` | Marg qty/value wide | `layouts/marg_qty_value_wide.py` |
| `stock_simple_7col` | Simple 7-column | `layouts/stock_simple_7col.py` |
| `marg_lms_simple` | Marg LMS columns | `layouts/marg_lms_simple.py` |
| `stock_rate_amount` | Rate + amount cols | `layouts/stock_rate_amount.py` |
| `stock_receipt_replace` | Receipt/replace stmt | `layouts/stock_receipt_replace.py` |
| `pharma_bytes_itemcode` | Pharma Bytes item-code | `layouts/pharma_bytes_itemcode.py` |
| `venus_stock_statement` | Venus | `layouts/venus_stock_statement.py` |
| `marg_opstk_statement` | Marg OpStk | `layouts/marg_opstk_statement.py` |
| `marg_bordered` | Marg bordered PDF table | `table_io.py` |
| `marg_web_stock` | Marg web stock report | `table_io.py` |
| `prompt_bordered` | Prompt ERP bordered | `table_io.py` |
| `dahod_marg` | Marg item-code register | `layouts/dahod_marg.py` |
| `saurashtra_monthly` | Logic ERP monthly | `layouts/saurashtra_monthly.py` |
| `generic` | Fallback | `layouts/generic.py` |

### Party Excel layouts

Package: `extractors/party_xlsx/`

| Layout key | Software | Module |
|---|---|---|
| `tabular_party_product` | EasyAC / generic tabular | `layouts/tabular_party_product.py` |
| `marg_busy` | Busy/Tally party-itemwise | `layouts/marg_busy.py` |
| `marg_register_excel` | Marg ERP register | `layouts/marg_register_excel.py` |
| `infosoft_bandwise` | Visual Infosoft | `layouts/infosoft_bandwise.py` |
| `jaimini_partywise` | Jaimini | `layouts/jaimini_partywise.py` |
| `painkiller_partywise` | Painkiller | `layouts/painkiller_partywise.py` |
| `data_spec_sale_by_item` | Data Spec | `layouts/data_spec_sale_by_item.py` |
| `fawin_partywise` | Fawin | `layouts/fawin_partywise.py` |
| `tabular` | Generic header-mapped | `layouts/tabular.py` |

### Stock Excel layouts

| Layout key | Software | Module |
|---|---|---|
| `marg_stock_wide` | Marg ERP wide report | `layouts/marg_stock_wide.py` |
| `venus_stock_excel` | Venus | `layouts/venus_stock_excel.py` |
| `marg_opstk_curstk` | Marg OpStk/CurStk | `layouts/marg_opstk_curstk.py` |
| `html_stock` | HTML export | `layouts/html_stock.py` |
| `tabular` | Generic header-mapped | `layouts/tabular.py` |

Stock rows must pass the sanity equation (see README). Changes to `postprocess.sanity_warnings()` affect scoring in `core/scoring.py`.

---

## 10. Regression test system

### Files

| Path | Purpose |
|---|---|
| `scripts/regression_test.py` | Runner |
| `tests/regression_manifest.json` | Suite definitions and data paths |
| `tests/baselines/<suite>/<file>.json` | Expected metrics per file |

### Commands

```bash
# List suites
python scripts/regression_test.py --list-suites

# Run CG party PDFs (39 files — baselines committed)
python scripts/regression_test.py --suite party_cg_pdf

# Run all suites that have baselines
python scripts/regression_test.py

# Refresh baselines after intentional parser improvement
python scripts/regression_test.py --suite party_cg_pdf --update
```

### What each baseline stores

- `row_count`, `party_count`, `area_count` (party routes)
- `detected_format` — layout/ERP key for **all routes** (party PDF, party Excel, stock PDF, stock Excel)
- `qty_total`, `amount_total` (party routes)
- `sample_parties`, `sample_products` (first 5, sorted)
- `warnings_count`

A failure prints exact field diffs — e.g. `row_count: expected 43, got 0`.

### Data paths

Manifest `reports_root` is `..` (the `Reports/` folder next to `pdf-spike/`):

```
Reports/
├── pdf-spike/          ← this repo
├── Party Wise/CG/      ← party_cg_pdf suite
├── Party Wise/GJ/
├── Party Wise/MP/
├── Party Wise/Partty-diff/
└── Sales Reports Wise/Sales Diff/
```

If test data is missing locally, suites skip gracefully. Baselines for `party_cg_pdf` are committed so CI/local runs work when CG files are present.

### When to update baselines

Update (`--update`) only when:

- You intentionally improved extraction (more rows, correct parties, fixed areas).
- You added a new file to the test folder.
- You changed canonical field mapping in a compatible way.

**Never update baselines to hide a regression.**

---

## 11. Anti-patterns (do not do these)

1. **Rewriting `detect_format()` from scratch** — breaks routing for all vendors.
2. **One parser per vendor** — e.g. `parse_rachit`, `parse_ganesh`, `parse_tirupati` when a shared layout parser exists.
3. **One mega-parser for all formats** — defeats the architecture.
4. **Hardcoding vendor names** in shared logic (e.g. `if "RACHIT" in text`) — use format detection and shared parser extensions instead.
5. **Removing skip/header filters** without testing — causes header lines to become data rows.
6. **Changing regex globally** without checking which `parse_*` functions use it.
7. **Skipping regression** because “it’s a small change”.
8. **Adding Streamlit caching** that hides code changes during development.

---

## 12. Pre-merge checklist

- [ ] Read this guide and identified **route + format** (not just vendor name)
- [ ] Confirmed scenario: new layout (§6) vs new vendor on existing layout (§7)
- [ ] Change is scoped to one **format-level** parser/helper (or new layout parser added)
- [ ] Did **not** add vendor-named parser or vendor-specific detect rule
- [ ] `detect_format` change is specific and ordered correctly
- [ ] `python scripts/regression_test.py --suite party_cg_pdf` passes
- [ ] Other affected suites tested if shared code changed
- [ ] Baselines updated only if metrics changed intentionally
- [ ] Output contract unchanged
- [ ] No unrelated refactors mixed in

---

## 13. Quick reference — which file to edit

| Task | Location |
|---|---|
| New Party PDF **layout** | `extractors/party_pdf/layouts/<layout>.py` + `detect.py` + `registry.py` |
| New vendor, **same** Party PDF layout | Extend existing `layouts/<layout>.py` only |
| Party name / area split | `extractors/party_pdf/party_area.py` |
| CID / unreadable PDF text | `extractors/party_pdf/pdf_io.py` → `_decode_cid()` |
| New Party Excel layout | `extractors/party_xlsx/layouts/<layout>.py` + `detect.py` + `registry.py` |
| New Stock PDF layout | `extractors/stock_pdf/layouts/<layout>.py` + `detect.py` + `registry.py` |
| New Stock Excel layout | `extractors/stock_xlsx/layouts/<layout>.py` + `detect.py` + `registry.py` |
| Layout display labels | `extractors/<route>/constants.py` → `LAYOUT_LABELS` or `FORMAT_LABELS` |
| Canonical field definitions | `core/canonical.py` |
| Header fuzzy matching | `core/header_match.py` |
| Score / coverage rules | `core/scoring.py` |
| UI tabs / routing | `app.py` |
| Regression baselines | `tests/baselines/<suite>/` via `scripts/regression_test.py --update` |

---

## 14. Example regression failure and fix

**Failure:**
```
FAIL RACHIT MEDICAL-COSMO.pdf
  - row_count: expected 43, got 0
  - detected_format: expected 'busy_tally', got 'unknown'
```

**Diagnosis:** Text is CID-encoded → `detect_format` never sees “Party / Item Wise”.

**Fix:** Apply `_decode_cid()` before format detection (already in place).

**Verify:**
```bash
python scripts/regression_test.py --suite party_cg_pdf
# All 39 OK
```

---

For project setup and route table, see [README.md](README.md).
