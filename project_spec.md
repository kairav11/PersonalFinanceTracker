# Wealth-Flow Lakehouse: Project Specification

**Version:** 1.0  
**Date:** 2026-05-09  
**Status:** Draft

---

## 1. Purpose & Scope

This document defines the functional requirements, data contracts, interface specifications, and acceptance criteria for the Wealth-Flow Lakehouse pipeline. It is the source of truth for what the system must do and how each component behaves.

**In scope:**
- Ingestion from Google Sheets and CSV files into Databricks Delta Lake
- Medallion Architecture transformation (Bronze → Silver → Gold) via dbt
- Fixed-rate multi-currency conversion (EUR base, USD, INR)
- Automated orchestration via GitHub Actions
- Public Streamlit dashboard hosted on Streamlit Community Cloud

**Out of scope:**
- Real-time / streaming ingestion
- Live exchange rate fetching
- Mobile app or native UI
- User authentication on the dashboard
- Multi-user / multi-account support

---

## 2. Functional Requirements

### FR-01: Google Sheets Ingestion
- The system SHALL read all rows from the `Transactions` tab of a configured Google Sheet on each scheduled run.
- The system SHALL read all rows from the `Budgets` tab of the same sheet on each scheduled run.
- The system SHALL append new transaction rows to `bronze.transactions` (never overwrite).
- The system SHALL overwrite `bronze.budgets` on each run (full refresh).
- The system SHALL tag every ingested row with `_source = 'google_sheets'` and `_ingested_at` (UTC timestamp).

### FR-02: CSV Ingestion
- The system SHALL process all `.csv` files found in `ingestion/csv_uploads/` when the workflow is triggered.
- The system SHALL validate that every CSV contains exactly the columns defined in §4.1.
- The system SHALL reject and skip any CSV that fails column validation, logging the filename and reason.
- The system SHALL append valid rows to `bronze.transactions` with `_source = 'csv_upload'`.
- The system SHALL move successfully processed CSVs to `ingestion/csv_uploads/processed/` after ingestion.
- The system SHALL NOT delete any CSV file — processed files are archived, not removed.

### FR-03: FX Conversion
- The system SHALL convert all transaction amounts to EUR using the fixed rates defined in `seeds/fx_rates.csv`.
- The system SHALL store the original `amount` and `currency` alongside `amount_eur` in Silver.
- The system SHALL support exactly three currencies: `EUR`, `USD`, `INR`.
- Any transaction with an unsupported `currency` value SHALL fail the dbt `accepted_values` test and block the Gold run.

### FR-04: Deduplication
- The system SHALL deduplicate `bronze.transactions` in the Silver layer using `transaction_id` as the primary key.
- When duplicate `transaction_id` values exist, the system SHALL retain only the row with the latest `_ingested_at` value.
- Deduplication SHALL occur regardless of `_source` — a row from a CSV and a row from Sheets with the same `transaction_id` are treated as duplicates.

### FR-05: Budget Tracking
- The system SHALL compute `actual_eur` vs `monthly_budget_eur` per category per month in `fct_budget_variance`.
- The system SHALL output an `over_budget` boolean flag (true when `actual_eur > budget_eur`).
- Categories with actual spend but no budget entry SHALL appear with `budget_eur = null` and `over_budget = null`.

### FR-06: Subscription Detection
- The system SHALL identify recurring merchants as those where the same `merchant` name appears in ≥ 3 distinct calendar months.
- Amount tolerance: charges are considered the same subscription if `amount_eur` is within ±2% of the median charge for that merchant.
- The output SHALL include `merchant`, `estimated_monthly_cost_eur`, `first_seen`, `last_seen`, `occurrence_count`.

### FR-07: Orchestration
- The scheduled pipeline SHALL run every 3 days at 00:00 UTC (`cron: '0 0 */3 * *'`).
- A `workflow_dispatch` trigger SHALL allow manual pipeline runs at any time.
- The CSV ingestion workflow SHALL trigger automatically on any push that adds or modifies files in `ingestion/csv_uploads/*.csv`.
- The CI workflow SHALL run on every pull request and block merging if `dbt compile` or `dbt test --select silver` fails.

### FR-08: Dashboard
- The dashboard SHALL display all 5 panels defined in §6.
- The dashboard SHALL be publicly accessible via a Streamlit Community Cloud URL without requiring login.
- The dashboard SHALL read exclusively from Gold layer tables.
- The dashboard SHALL handle an empty Gold table gracefully (show an empty state, not an error).

---

## 3. Non-Functional Requirements

| ID | Requirement | Target |
|---|---|---|
| NFR-01 | Pipeline end-to-end run time | < 10 minutes |
| NFR-02 | Databricks compute hours per run | < 0.5 DBU |
| NFR-03 | dbt test pass rate to proceed to Gold | 100% (zero tolerance) |
| NFR-04 | Dashboard cold load time | < 5 seconds |
| NFR-05 | GitHub Actions secrets — zero plaintext credentials in code | All secrets via GitHub Secrets / Streamlit Secrets |
| NFR-06 | CSV validation error messages | Human-readable, include filename + column diff |
| NFR-07 | Processed CSVs retained for | Indefinitely (in `processed/` folder) |

---

## 4. Data Contracts

### 4.1 Bronze: `transactions`

| Column | Type | Nullable | Constraint |
|---|---|---|---|
| `transaction_id` | STRING | NO | User-provided; not enforced unique at Bronze |
| `date` | STRING | NO | Raw string; cast to DATE in Silver |
| `merchant` | STRING | NO | |
| `amount` | STRING | NO | Raw string; cast to DECIMAL(18,2) in Silver |
| `currency` | STRING | NO | Raw string; validated in Silver |
| `type` | STRING | NO | Raw string; validated in Silver |
| `category` | STRING | YES | |
| `account` | STRING | YES | |
| `notes` | STRING | YES | |
| `_source` | STRING | NO | `'google_sheets'` or `'csv_upload'` |
| `_ingested_at` | TIMESTAMP | NO | UTC, set by ingestion script |

> Bronze is append-only and stores raw strings. No casting or validation occurs here — that is Silver's job.

### 4.2 Bronze: `budgets`

| Column | Type | Nullable |
|---|---|---|
| `category` | STRING | NO |
| `monthly_budget_eur` | STRING | NO |
| `_ingested_at` | TIMESTAMP | NO |

### 4.3 Silver: `stg_transactions`

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `transaction_id` | STRING | NO | Deduplicated primary key |
| `date` | DATE | NO | Cast from string |
| `merchant` | STRING | NO | |
| `amount` | DECIMAL(18,2) | NO | Original amount |
| `currency` | STRING | NO | Validated: EUR / USD / INR |
| `amount_eur` | DECIMAL(18,4) | NO | `amount * rate_to_eur` from seed |
| `type` | STRING | NO | Validated: income / expense |
| `category` | STRING | YES | |
| `account` | STRING | YES | |
| `notes` | STRING | YES | |
| `_source` | STRING | NO | Carried from Bronze |
| `_ingested_at` | TIMESTAMP | NO | Latest value after dedup |

### 4.4 Silver: `stg_budgets`

| Column | Type | Nullable |
|---|---|---|
| `category` | STRING | NO |
| `monthly_budget_eur` | DECIMAL(18,2) | NO |

### 4.5 Seed: `fx_rates`

| Column | Type | Value |
|---|---|---|
| `currency` | STRING | `EUR`, `USD`, `INR` |
| `rate_to_eur` | DECIMAL(10,6) | `1.0`, `0.926`, `0.011` |

### 4.6 Gold: `fct_monthly_burn`

| Column | Type | Notes |
|---|---|---|
| `year_month` | STRING | Format: `YYYY-MM` |
| `category` | STRING | |
| `type` | STRING | `income` or `expense` |
| `total_eur` | DECIMAL(18,2) | |
| `ytd_total_eur` | DECIMAL(18,2) | Running total within calendar year |

### 4.7 Gold: `fct_budget_variance`

| Column | Type | Notes |
|---|---|---|
| `year_month` | STRING | |
| `category` | STRING | |
| `actual_eur` | DECIMAL(18,2) | |
| `budget_eur` | DECIMAL(18,2) | Null if no budget set |
| `variance_eur` | DECIMAL(18,2) | `actual - budget`; positive = over budget |
| `variance_pct` | DECIMAL(8,2) | Null if no budget set |
| `over_budget` | BOOLEAN | Null if no budget set |

### 4.8 Gold: `fct_income_vs_expense`

| Column | Type | Notes |
|---|---|---|
| `year_month` | STRING | |
| `total_income_eur` | DECIMAL(18,2) | |
| `total_expense_eur` | DECIMAL(18,2) | |
| `net_eur` | DECIMAL(18,2) | `income - expense` |
| `rolling_3m_avg_net_eur` | DECIMAL(18,2) | 3-month rolling average of `net_eur` |

### 4.9 Gold: `dim_subscription_tracker`

| Column | Type | Notes |
|---|---|---|
| `merchant` | STRING | |
| `estimated_monthly_cost_eur` | DECIMAL(18,2) | Median `amount_eur` across charges |
| `first_seen` | DATE | |
| `last_seen` | DATE | |
| `occurrence_count` | INTEGER | Distinct months with a charge |

---

## 5. Interface Specifications

### 5.1 Google Sheets API
- **Auth method:** Service Account (OAuth 2.0, server-to-server)
- **Scope required:** `https://www.googleapis.com/auth/spreadsheets.readonly`
- **Sheet structure:** Single spreadsheet, two named tabs: `Transactions` and `Budgets`
- **Row 1:** Header row matching column names in §4.1 and §4.2 exactly (case-sensitive)
- **Credential storage:** Full JSON key contents stored in `GOOGLE_SERVICE_ACCOUNT_JSON` GitHub Secret

### 5.2 CSV Upload Interface
- **Drop location:** `ingestion/csv_uploads/` directory in the repository
- **Required headers:** Exactly the 9 columns in §4.1 (`transaction_id`, `date`, `merchant`, `amount`, `currency`, `type`, `category`, `account`, `notes`)
- **Template file:** `ingestion/csv_uploads/template.csv` committed to the repo
- **Date format:** `YYYY-MM-DD`
- **Amount format:** Decimal number, no currency symbols, no commas (e.g. `1500.00`)
- **Encoding:** UTF-8
- **Trigger:** Committing any `.csv` to `csv_uploads/` triggers `csv_ingest.yml` automatically

### 5.3 Databricks Connection
- **Connection:** `databricks-sql-connector` Python library
- **Auth:** Personal Access Token via `DATABRICKS_TOKEN`
- **Metastore:** Unity Catalog — `workspace` catalog (Community Edition workspace)
- **Table naming:** Three-part `workspace.schema.table` (e.g. `workspace.gold.fct_monthly_burn`)
- **Dashboard queries:** Read-only SELECT against Gold tables only

### 5.4 Streamlit Dashboard
- **Framework:** Streamlit
- **Charting library:** Plotly Express
- **Secret management:** Streamlit Community Cloud secrets UI (`DATABRICKS_HOST`, `DATABRICKS_TOKEN`, `DATABRICKS_HTTP_PATH`)
- **Caching:** `@st.cache_data(ttl=3600)` on all Databricks query functions (1-hour cache)
- **Deployment:** Streamlit Community Cloud, connected to the `dashboard/` folder of the GitHub repo
- **Visibility:** Public (no login required)

---

## 6. Dashboard Panel Specifications

### Panel 1 — Monthly Burn by Category
- **Chart:** Plotly stacked bar chart
- **X-axis:** `year_month`
- **Y-axis:** `total_eur`
- **Color:** `category`
- **Filter:** `type = 'expense'`
- **Source:** `fct_monthly_burn`

### Panel 2 — Budget Variance
- **Chart:** Plotly grouped bar chart
- **X-axis:** `category`
- **Y-axis:** `actual_eur` and `budget_eur` (grouped bars)
- **Color coding:** Bar turns red when `over_budget = true`
- **Filter:** Month selector (default: current month)
- **Source:** `fct_budget_variance`

### Panel 3 — Income vs. Expense
- **Chart:** Plotly dual-line chart
- **X-axis:** `year_month`
- **Lines:** `total_income_eur`, `total_expense_eur`, `net_eur`
- **Source:** `fct_income_vs_expense`

### Panel 4 — Subscriptions
- **Chart:** Sortable Streamlit dataframe
- **Columns shown:** `merchant`, `estimated_monthly_cost_eur`, `occurrence_count`, `first_seen`, `last_seen`
- **Sorted by:** `estimated_monthly_cost_eur` descending
- **Source:** `dim_subscription_tracker`

### Panel 5 — YTD Summary
- **Chart:** 3 Streamlit `st.metric` KPI tiles
- **Metrics:** `YTD Total Spent (EUR)`, `YTD Total Earned (EUR)`, `YTD Net Savings (EUR)`
- **Source:** `fct_income_vs_expense` (filtered to current year, summed)

---

## 7. dbt Model Specifications

### Materialization Strategy

| Layer | Materialization | Reason |
|---|---|---|
| Silver | `table` | Deduplication requires a full scan; tables are faster to query downstream |
| Gold | `table` | Dashboard queries need low latency; recomputed on each pipeline run |
| Seeds | `seed` | Static reference data; committed to repo |

### Incremental Strategy
All models use full-refresh materialization for simplicity and correctness at this data volume. Incremental models are not needed within the Databricks Free Edition compute budget.

### Run Order (enforced by dbt refs)
```
bronze.transactions
bronze.budgets
seeds.fx_rates
    ↓
silver.stg_transactions  ←  refs: bronze.transactions, seeds.fx_rates
silver.stg_budgets       ←  refs: bronze.budgets
    ↓
gold.fct_monthly_burn       ←  refs: silver.stg_transactions
gold.fct_income_vs_expense  ←  refs: silver.stg_transactions
gold.fct_budget_variance    ←  refs: gold.fct_monthly_burn, silver.stg_budgets
gold.dim_subscription_tracker ← refs: silver.stg_transactions
```

---

## 8. Error Handling & Logging

### Ingestion Scripts
- All scripts use Python `logging` at INFO level by default; ERROR on failures.
- A failed Google Sheets API call SHALL raise an exception and fail the GitHub Actions step (non-zero exit code).
- A CSV with invalid columns SHALL log `ERROR: [filename] rejected — missing columns: [list]` and continue processing other CSVs. The workflow step does NOT fail if at least one CSV succeeds; it DOES fail if all CSVs are invalid.
- Network errors on API calls SHALL retry up to 3 times with exponential backoff before failing.

### dbt Pipeline
- Any failing dbt test in the Silver layer SHALL halt the pipeline — the Gold run will not execute.
- dbt run failures write to GitHub Actions logs automatically.
- `dbt source freshness` is not configured (no dbt sources defined — Bronze tables are referenced directly).

### Dashboard
- If a Gold table returns zero rows, each panel displays a styled empty-state message (`st.info("No data available yet.")`).
- If the Databricks connection fails at dashboard load, `st.error()` is displayed with the exception message.

---

## 9. Testing Strategy

### dbt Schema Tests (automated, run in CI and pipeline)
- `not_null` on all primary and foreign keys
- `unique` on all grain-level keys
- `accepted_values` on `currency`, `type`
- `dbt_utils.expression_is_true` for `amount > 0`, `rate_to_eur > 0`

### Manual Validation Checklist (Day 7)
- [ ] Duplicate `transaction_id` rows resolve correctly in Silver (latest `_ingested_at` wins)
- [ ] A USD transaction of 100 USD appears as 92.60 EUR in Silver
- [ ] An INR transaction of 1000 INR appears as 11.00 EUR in Silver
- [ ] A merchant appearing 4 times appears in `dim_subscription_tracker`; one appearing twice does not
- [ ] An over-budget category shows `over_budget = true` in `fct_budget_variance`
- [ ] A CSV with a missing column is rejected and logs the column name; other CSVs in the same run still process
- [ ] Pipeline runs end-to-end in < 10 minutes

---

## 10. Repository Structure

```
wealth-flow-lakehouse/
├── .github/
│   └── workflows/
│       ├── pipeline.yml          (scheduled + manual full pipeline)
│       ├── csv_ingest.yml        (triggered on csv_uploads/* push)
│       └── ci.yml                (PR validation)
├── ingestion/
│   ├── ingest_bronze.py          (Google Sheets → Bronze)
│   ├── ingest_csv.py             (CSV → Bronze)
│   ├── generate_dummy_data.py    (test data generator)
│   ├── requirements.txt          (gspread, databricks-sql-connector, etc.)
│   └── csv_uploads/
│       ├── .gitkeep
│       ├── template.csv          (schema reference for CSV uploads)
│       └── processed/            (successfully ingested CSVs archived here)
├── wealth_flow_dbt/
│   ├── dbt_project.yml
│   ├── profiles.yml
│   ├── seeds/
│   │   └── fx_rates.csv
│   └── models/
│       ├── silver/
│       │   ├── schema.yml
│       │   ├── stg_transactions.sql
│       │   └── stg_budgets.sql
│       └── gold/
│           ├── schema.yml
│           ├── fct_monthly_burn.sql
│           ├── fct_budget_variance.sql
│           ├── fct_income_vs_expense.sql
│           └── dim_subscription_tracker.sql
├── dashboard/
│   ├── app.py
│   ├── requirements.txt
│   └── .streamlit/
│       └── secrets.toml.example
├── project_plan.md
├── project_spec.md               (this document)
└── README.md
```

---

## 11. Open Questions / Future Enhancements

| Item | Notes |
|---|---|
| Auto-generate `transaction_id` | Google Apps Script in the Sheet could auto-fill UUIDs on new rows |
| More currencies | Add rows to `fx_rates.csv` — no code change needed |
| Live FX rates | Swap seed for a Bronze table populated by an API call; Silver join stays the same |
| Incremental dbt models | Worth adding if data volume grows beyond ~100k rows |
| Dashboard authentication | Streamlit has a built-in auth option if the dashboard needs to go private |
| dbt docs site | `dbt docs generate && dbt docs serve` for a data catalog view |
