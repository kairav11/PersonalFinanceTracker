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
- Databricks workspace ([Community Edition](https://community.cloud.databricks.com/) works — free)
- Google Cloud project with a service account granted `spreadsheets.readonly` scope
- A Google Sheet with `Transactions` and `Budgets` tabs — see [`ingestion/csv_uploads/template.csv`](ingestion/csv_uploads/template.csv) for the required column schema

### Template files

Three example files are provided — copy and fill them in before running anything:

| Example file | Copy to | Used by |
|---|---|---|
| [`.env.example`](.env.example) | `.env` | All ingestion scripts and dbt |
| [`dashboard/.streamlit/secrets.toml.example`](dashboard/.streamlit/secrets.toml.example) | `.streamlit/secrets.toml` (project root) | Streamlit dashboard (local) |
| [`ingestion/csv_uploads/template.csv`](ingestion/csv_uploads/template.csv) | `ingestion/csv_uploads/your_file.csv` | CSV ingestion |

```bash
cp .env.example .env
cp dashboard/.streamlit/secrets.toml.example .streamlit/secrets.toml
# Edit both files and fill in your credentials
```

### Key environment variables

| Variable | Where to find it |
|---|---|
| `DATABRICKS_HOST` | Databricks UI → workspace URL (hostname only, no `https://`) |
| `DATABRICKS_HTTP_PATH` | SQL Warehouses → your warehouse → Connection details |
| `DATABRICKS_TOKEN` | User Settings → Developer → Access Tokens |
| `GOOGLE_SHEET_ID` | The long ID in your Sheet URL between `/d/` and `/edit` |
| `GOOGLE_SERVICE_ACCOUNT_JSON_PATH` | Path to your downloaded service account key JSON |

### Run ingestion

```bash
pip install -r ingestion/requirements.txt
source .env

# Option A — ingest from Google Sheets (transactions + budgets)
python ingestion/ingest_bronze.py

# Option B — ingest from CSV files dropped in csv_uploads/
python ingestion/ingest_csv.py

# Option C — generate 6 months of dummy data into the Sheet (useful for testing)
python ingestion/generate_dummy_data.py
```

### Run dbt

```bash
pip install dbt-databricks==1.11.7
source .env

# Full pipeline: seed FX rates → Silver → test → Gold
dbt seed --project-dir wealth_flow_dbt && \
dbt run --select silver --project-dir wealth_flow_dbt && \
dbt test --select silver --project-dir wealth_flow_dbt && \
dbt run --select gold --project-dir wealth_flow_dbt
```

### Run dashboard locally

```bash
pip install -r dashboard/requirements.txt
# .streamlit/secrets.toml must exist at the project root (see template files above)
streamlit run dashboard/app.py
```

---

## Project Structure

```
.
├── .env.example                        # ← copy to .env and fill in credentials
├── runtime.txt                         # Pins Python 3.12 for Streamlit Community Cloud
├── ingestion/
│   ├── ingest_bronze.py                # Google Sheets → bronze.transactions + bronze.budgets
│   ├── ingest_csv.py                   # CSV files → bronze.transactions
│   ├── generate_dummy_data.py          # Seed Google Sheet with 6 months of test data
│   ├── requirements.txt
│   └── csv_uploads/
│       ├── template.csv                # ← copy and populate for CSV ingestion
│       └── processed/                  # Ingested CSVs are archived here automatically
├── wealth_flow_dbt/
│   ├── models/silver/                  # stg_transactions, stg_budgets
│   ├── models/gold/                    # fct_monthly_burn, fct_income_vs_expense,
│   │                                   # fct_budget_variance, dim_subscription_tracker
│   ├── seeds/fx_rates.csv              # Fixed FX rates
│   └── macros/                         # generate_schema_name override for Unity Catalog
├── dashboard/
│   ├── app.py                          # Streamlit dashboard (reads Gold only)
│   ├── ingest.py                       # Local CSV upload UI (not deployed to Cloud)
│   ├── requirements.txt
│   └── .streamlit/
│       └── secrets.toml.example        # ← copy to .streamlit/secrets.toml at project root
└── .github/workflows/
    ├── pipeline.yml                    # Daily full pipeline (06:00 UTC)
    ├── csv_ingest.yml                  # Triggered on push to csv_uploads/*.csv
    └── ci.yml                          # dbt compile + Silver tests on every PR
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
