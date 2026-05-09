# Wealth-Flow Lakehouse

A personal finance analytics pipeline built on the **Medallion Architecture** — raw transactions flow from Google Sheets and CSV uploads through Databricks Delta Lake, transformed by dbt, and surfaced on a live Streamlit dashboard.

**[View Live Dashboard →](https://personalfinancetracker-tatakmyfok6dkfwznksfc5.streamlit.app)**

---

## Architecture

```
Google Sheets ──┐
                ├──▶ Bronze (raw append-only) ──▶ Silver (clean + dedup) ──▶ Gold (aggregated) ──▶ Streamlit
CSV Uploads  ───┘
```

| Layer | Table | Description |
|---|---|---|
| Bronze | `workspace.bronze.transactions` | Raw ingested rows, append-only, strings only |
| Bronze | `workspace.bronze.budgets` | Full-overwrite on each run |
| Silver | `workspace.silver.stg_transactions` | Deduplicated, type-cast, FX-converted to EUR |
| Silver | `workspace.silver.stg_budgets` | Validated budget rows |
| Gold | `workspace.gold.fct_monthly_burn` | Monthly spend by category with YTD running totals |
| Gold | `workspace.gold.fct_income_vs_expense` | Monthly income, expense, net, and 3-month rolling avg |
| Gold | `workspace.gold.fct_budget_variance` | Actual vs budget per category with over-budget flag |
| Gold | `workspace.gold.dim_subscription_tracker` | Auto-detected recurring merchants |

---

## Tech Stack

| Component | Technology |
|---|---|
| Data warehouse | Databricks Community Edition (Unity Catalog) |
| Transformation | dbt Core 1.11 + dbt-databricks + dbt_utils |
| Ingestion | Python 3.12, `databricks-sql-connector`, `gspread` |
| Orchestration | GitHub Actions (daily at 06:00 UTC + push triggers) |
| Dashboard | Streamlit 1.35, Plotly, hosted on Streamlit Community Cloud |
| FX rates | Fixed seed (EUR base: 1 USD = 0.926 EUR, 1 INR = 0.011 EUR) |

---

## Dashboard Panels

- **YTD Summary** — total earned, total spent, and net savings year-to-date vs prior year
- **Monthly Burn by Category** — stacked bar chart of expenses over time
- **Income vs. Expense** — line chart with income, expense, and net cash flow trends
- **Budget Variance** — actual vs. configured budget per category with over-budget callouts
- **Recurring Subscriptions** — auto-detected merchants charging consistently each month

---

## Local Setup

### Prerequisites
- Python 3.12
- Databricks workspace (Community Edition works)
- Google Cloud service account with `spreadsheets.readonly` scope
- A Google Sheet with `Transactions` and `Budgets` tabs matching the schema in `ingestion/csv_uploads/template.csv`

### Environment variables

```bash
cp .env.example .env   # fill in your values
```

| Variable | Description |
|---|---|
| `DATABRICKS_HOST` | e.g. `adb-xxxx.azuredatabricks.net` |
| `DATABRICKS_HTTP_PATH` | SQL Warehouse HTTP path |
| `DATABRICKS_TOKEN` | Personal access token |
| `GOOGLE_SHEET_ID` | ID from the Sheet URL |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Full service account JSON (as a string) |

### Run ingestion

```bash
pip install -r ingestion/requirements.txt
source .env

# Ingest from Google Sheets
python ingestion/ingest_bronze.py

# Ingest from CSV files in ingestion/csv_uploads/
python ingestion/ingest_csv.py
```

### Run dbt

```bash
pip install dbt-databricks==1.11.7
source .env

cd wealth_flow_dbt
dbt seed && dbt run --select silver && dbt test --select silver && dbt run --select gold
```

### Run dashboard locally

```bash
pip install -r dashboard/requirements.txt

# Create .streamlit/secrets.toml from the example
cp dashboard/.streamlit/secrets.toml.example .streamlit/secrets.toml
# Fill in your Databricks credentials

streamlit run dashboard/app.py
```

---

## Project Structure

```
.
├── ingestion/
│   ├── ingest_bronze.py        # Google Sheets → bronze.transactions + bronze.budgets
│   ├── ingest_csv.py           # CSV files → bronze.transactions
│   ├── generate_dummy_data.py  # Seed Google Sheet with 6 months of test data
│   └── csv_uploads/            # Drop CSVs here; processed/ archives ingested files
├── wealth_flow_dbt/
│   ├── models/silver/          # stg_transactions, stg_budgets
│   ├── models/gold/            # fct_monthly_burn, fct_income_vs_expense,
│   │                           # fct_budget_variance, dim_subscription_tracker
│   ├── seeds/fx_rates.csv      # Fixed FX rates
│   └── macros/                 # generate_schema_name override for Unity Catalog
├── dashboard/
│   ├── app.py                  # Streamlit dashboard (reads Gold only)
│   └── ingest.py               # Local CSV upload UI (not deployed)
└── .github/workflows/
    ├── pipeline.yml            # Daily full pipeline
    ├── csv_ingest.yml          # Triggered on CSV push
    └── ci.yml                  # dbt compile + Silver tests on every PR
```

---

## Key Design Decisions

| Decision | Choice | Reason |
|---|---|---|
| FX rates | Fixed seed file | Auditable; no rate-limit or API dependency |
| Deduplication | Latest `_ingested_at` wins | Idempotent re-ingestion safe |
| Materialization | Full-refresh tables | Correct and simple at this data volume |
| Budget source | Google Sheets tab | No dbt seed churn when budgets change |
| Subscription detection | ≥ 3 months, charges within ±2% of median | Catches recurring charges, ignores one-offs |

---

## GitHub Actions

| Workflow | Trigger | Steps |
|---|---|---|
| `pipeline.yml` | Daily 06:00 UTC + manual | Sheets ingest → seed → silver → test → gold |
| `csv_ingest.yml` | Push to `csv_uploads/*.csv` | CSV ingest → silver → test → gold |
| `ci.yml` | Every PR | `dbt compile` + `dbt test --select silver` |

All workflows use SHA-pinned actions and read secrets from GitHub Secrets only.
