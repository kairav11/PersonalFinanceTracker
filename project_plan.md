# Wealth-Flow Lakehouse: Enterprise Personal Finance Engineering

## 1. What I Am Building

Wealth-Flow Lakehouse is a production-grade Data Lakehouse built on **Databricks**, designed to automate personal financial auditing. Moving beyond traditional spreadsheets, this project implements a professional **Medallion Architecture** using **dbt**, **Delta Lake**, and **Unity Catalog** (Databricks `workspace` catalog).

The pipeline ingests personal transaction and budget data from **Google Sheets** and/or **CSV uploads**, converts all amounts to **EUR** via fixed exchange rates, and produces business-level analytical views surfaced in a publicly hosted **Streamlit dashboard** — automatically refreshed every 3 days via **GitHub Actions**.

---

## 2. Tech Stack

| Layer | Tool | Purpose |
|---|---|---|
| Source A | Google Sheets (2 tabs) | Manual data entry interface |
| Source B | CSV uploads (`csv_uploads/`) | Bulk import from any export |
| Infrastructure | Databricks Community Edition | Spark cluster + Unity Catalog (`workspace`) |
| Storage | Delta Lake | ACID-compliant, versioned storage |
| FX Rates | dbt seed (`fx_rates.csv`) | Fixed EUR conversion rates |
| Transformation | dbt Core v1.8+ (`dbt-databricks`) | All Silver/Gold logic |
| Orchestration | GitHub Actions | CI/CD + 3-day scheduled pipeline + CSV trigger |
| Secrets | GitHub Secrets | Databricks token, Google credentials |
| Visualization | Streamlit Community Cloud | Free, publicly hosted dashboard |

---

## 3. System Architecture

```
Google Sheets (Transactions + Budgets)
          +
CSV files in csv_uploads/
          |
          v
  [Python Ingestion Scripts]
          |
          v
╔══════════════════════════════════╗
║   BRONZE LAYER (Raw Delta)       ║
║   bronze.*          (Hive DB)    ║
║   - transactions  (_source tag)  ║
║   - budgets                      ║
╚══════════════════════════════════╝
          |
          v  (dbt)
╔══════════════════════════════════╗
║   SILVER LAYER (Curated)         ║
║   silver.*          (Hive DB)    ║
║   - stg_transactions             ║
║   - stg_budgets                  ║
╚══════════════════════════════════╝
          |                  ^
          v  (dbt)           |
╔══════════════════════════════════╗
║   dbt SEED                       ║
║   seeds/fx_rates.csv             ║
║   (EUR / USD / INR — fixed)      ║
╚══════════════════════════════════╝
          |
          v
╔══════════════════════════════════╗
║   GOLD LAYER (Analytical)        ║
║   gold.*            (Hive DB)    ║
║   - fct_monthly_burn             ║
║   - fct_budget_variance          ║
║   - fct_income_vs_expense        ║
║   - dim_subscription_tracker     ║
╚══════════════════════════════════╝
          |
          v
  Streamlit Dashboard
  (Streamlit Community Cloud — public URL)
```

The pipeline runs every 3 days at midnight UTC, and also triggers automatically when CSVs are pushed to `csv_uploads/`.

---

## 4. Data Schema

### 4.1 Google Sheet — Tab 1: `Transactions`
*(CSV uploads must use this exact schema)*

| Column | Type | Description | Example |
|---|---|---|---|
| `transaction_id` | String | UUID — primary key, user-generated | `txn_abc123` |
| `date` | Date | Transaction date (YYYY-MM-DD) | `2025-05-01` |
| `merchant` | String | Payee or income source name | `Netflix` |
| `amount` | Decimal | Absolute value — always positive | `15.99` |
| `currency` | String | `EUR`, `USD`, or `INR` | `EUR` |
| `type` | String | `income` or `expense` | `expense` |
| `category` | String | Must match taxonomy in §4.3 | `Subscriptions` |
| `account` | String | Bank or card used | `HDFC Savings` |
| `notes` | String | Optional free-text | `Monthly plan` |

> **Deduplication key:** `transaction_id`. If the same ID appears multiple times in Bronze (e.g. re-ingested rows), only the latest version is kept in Silver.
> **Default currency:** EUR. Transactions with no currency value should default to EUR.

### 4.2 Google Sheet — Tab 2: `Budgets`

| Column | Type | Description | Example |
|---|---|---|---|
| `category` | String | Must match expense taxonomy | `Food & Dining` |
| `monthly_budget_eur` | Decimal | Monthly budget in EUR | `450.00` |

### 4.3 Category Taxonomy

**Expense categories:**
`Housing` · `Food & Dining` · `Transportation` · `Entertainment` · `Shopping` · `Healthcare` · `Utilities` · `Subscriptions` · `Education` · `Travel` · `Personal Care` · `Other`

**Income categories:**
`Salary` · `Freelance` · `Investment Returns` · `Other Income`

---

## 5. Multi-Currency / FX Handling

Exchange rates are **fixed** and stored as a dbt seed (`seeds/fx_rates.csv`). No external API is needed.

**Base currency: EUR.** All amounts in Gold are reported in EUR.

### Fixed Rates (`seeds/fx_rates.csv`)

| currency | rate_to_eur | description |
|---|---|---|
| EUR | 1.0 | Base currency |
| USD | 0.926 | 1 USD = 0.926 EUR |
| INR | 0.011 | 1 INR = 0.011 EUR |

### How it works
- Bronze stores `amount` and `currency` exactly as entered.
- Silver `stg_transactions` joins to `ref('fx_rates')` on `currency` and adds `amount_eur = amount * rate_to_eur`.
- All Gold models aggregate on `amount_eur` only.
- Original `amount` and `currency` are preserved in Silver for auditability.

> To update rates in the future, edit `fx_rates.csv`, commit, and the next dbt run picks up the change automatically.

---

## 6. Database Structure (Unity Catalog — `workspace` catalog)

Tables use three-part Unity Catalog naming: `workspace.schema.table`.

```
Unity Catalog: workspace
├── Schema: bronze
│   ├── transactions    (raw from all sources — append-only, _source tagged)
│   └── budgets         (raw from Google Sheets — full overwrite each run)
├── Schema: silver
│   ├── stg_transactions  (deduplicated, typed, amount_eur added)
│   └── stg_budgets       (typed, validated)
└── Schema: gold
    ├── fct_monthly_burn         (monthly spend + income by category, EUR)
    ├── fct_budget_variance      (actual vs. budgeted by category + month)
    ├── fct_income_vs_expense    (net cash flow by month)
    └── dim_subscription_tracker (recurring charge detection)
```

Create these databases once in a Databricks notebook before running the pipeline:
```sql
CREATE DATABASE IF NOT EXISTS bronze;
CREATE DATABASE IF NOT EXISTS silver;
CREATE DATABASE IF NOT EXISTS gold;
```

---

## 7. dbt Project Structure

```
wealth_flow_dbt/
├── dbt_project.yml
├── profiles.yml                   (Databricks connection via env vars)
├── seeds/
│   └── fx_rates.csv               (fixed EUR conversion rates)
├── models/
│   ├── silver/
│   │   ├── schema.yml             (tests for all silver models)
│   │   ├── stg_transactions.sql   (dedup, cast, join fx_rates → amount_eur)
│   │   └── stg_budgets.sql
│   └── gold/
│       ├── schema.yml             (tests for all gold models)
│       ├── fct_monthly_burn.sql
│       ├── fct_budget_variance.sql
│       ├── fct_income_vs_expense.sql
│       └── dim_subscription_tracker.sql
└── macros/
    └── (utility macros if needed)
```

**dbt Tests:**
- `stg_transactions`: `transaction_id` not null + unique, `amount` > 0, `type` in [`income`, `expense`], `currency` in [`EUR`, `USD`, `INR`]
- `stg_budgets`: `category` not null + unique, `monthly_budget_eur` > 0
- `fx_rates` seed: `currency` not null + unique, `rate_to_eur` > 0

---

## 8. Gold Layer Logic

### `fct_monthly_burn`
Monthly total spend and income per category in EUR. Includes running YTD totals.
Grain: one row per `(year_month, category, type)`.

### `fct_budget_variance`
Joins `fct_monthly_burn` (expense rows only) to `stg_budgets`.
Outputs: `actual_eur`, `budget_eur`, `variance_eur`, `variance_pct`, `over_budget` (boolean).
Grain: one row per `(year_month, category)`.

### `fct_income_vs_expense`
Monthly: total income, total expenses, net cash flow in EUR. Includes 3-month rolling average net.
Grain: one row per `year_month`.

### `dim_subscription_tracker`
Detects recurring charges: same merchant, same amount (±2%), appearing ≥ 3 times across distinct months.
Outputs: `merchant`, `estimated_monthly_cost_eur`, `first_seen`, `last_seen`, `occurrence_count`.
Grain: one row per recurring merchant.

---

## 9. Ingestion Architecture

### `ingestion/ingest_bronze.py` — Google Sheets source
- Authenticates via **Service Account** (JSON key from `GOOGLE_SERVICE_ACCOUNT_JSON` GitHub Secret)
- Reads `Transactions` tab → appends to `bronze.transactions` with `_source = 'google_sheets'`
- Reads `Budgets` tab → overwrites `bronze.budgets`
- Adds `_ingested_at` timestamp to every row

### `ingestion/ingest_csv.py` — CSV upload source
- Scans all `.csv` files in `ingestion/csv_uploads/`
- Validates that columns match the schema in §4.1 — raises a clear error if not
- Appends valid rows to `bronze.transactions` with `_source = 'csv_upload'`
- Moves processed files to `ingestion/csv_uploads/processed/` (preserves originals for audit)
- Adds `_ingested_at` timestamp to every row
- A `csv_uploads/template.csv` is committed to the repo showing the required headers

### `ingestion/generate_dummy_data.py` — Test data generator
- Generates 6 months of realistic dummy transactions across EUR, USD, and INR
- Covers all expense + income categories
- Includes 3+ recurring merchants to validate subscription detection
- Writes directly to the Google Sheet (and optionally outputs a CSV for the CSV path test)

---

## 10. GitHub Actions Orchestration

### `.github/workflows/pipeline.yml` — Scheduled every 3 days
```yaml
on:
  schedule:
    - cron: '0 0 */3 * *'
  workflow_dispatch:        # allows manual trigger
```

**Pipeline steps (sequential):**
1. Run `ingest_bronze.py` (Google Sheets → Bronze)
2. `dbt seed` (load/refresh `fx_rates.csv`)
3. `dbt run --select silver`
4. `dbt test --select silver`
5. `dbt run --select gold`

### `.github/workflows/csv_ingest.yml` — Triggered on CSV push
```yaml
on:
  push:
    paths:
      - 'ingestion/csv_uploads/*.csv'
```

**Steps:**
1. Run `ingest_csv.py` (CSV files → Bronze)
2. `dbt run --select silver gold`

> This means you can add data anytime just by committing a CSV — no manual pipeline trigger needed.

### `.github/workflows/ci.yml` — Runs on every PR
1. `dbt compile` (syntax + dependency check)
2. `dbt test --select silver` (data quality gate)

### Required GitHub Secrets

| Secret Name | Contents |
|---|---|
| `DATABRICKS_HOST` | Workspace URL (e.g. `https://adb-xxxx.azuredatabricks.net`) |
| `DATABRICKS_TOKEN` | Personal access token |
| `DATABRICKS_HTTP_PATH` | SQL Warehouse HTTP path |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Full contents of the service account JSON key |
| `GOOGLE_SHEET_ID` | Spreadsheet ID from the Google Sheets URL |

---

## 11. Dashboard — Streamlit (Public, Free)

### Why Streamlit
- **Free hosting** on Streamlit Community Cloud (`streamlit.io/cloud`)
- **Public URL** — share a single link with recruiters, no login required
- Reads directly from Databricks SQL Gold tables via `databricks-sql-connector`
- Looks professional and is widely recognised in the data/ML community

### Project structure
```
dashboard/
├── app.py                      (main Streamlit app)
├── requirements.txt            (streamlit, databricks-sql-connector, plotly, pandas)
└── .streamlit/
    └── secrets.toml.example    (template — actual secrets set in Streamlit Cloud UI)
```

### Dashboard Panels

| Panel | Chart Type | Source Model | Description |
|---|---|---|---|
| Monthly Burn by Category | Stacked bar | `fct_monthly_burn` | EUR spend per category per month |
| Budget Variance | Bar chart | `fct_budget_variance` | Actual vs. budget, red/green coded |
| Income vs. Expense | Line chart | `fct_income_vs_expense` | Monthly net cash flow trend in EUR |
| Subscriptions | Table | `dim_subscription_tracker` | Recurring charges with monthly EUR cost |
| YTD Summary | KPI tiles | `fct_income_vs_expense` | Total spent, earned, net savings |

### Deployment steps
1. Push `dashboard/` to GitHub
2. Go to `share.streamlit.io` → connect GitHub repo → select `dashboard/app.py`
3. In Streamlit Cloud settings, add `DATABRICKS_HOST`, `DATABRICKS_TOKEN`, `DATABRICKS_HTTP_PATH` as secrets
4. App is live at a public `*.streamlit.app` URL — no authentication wall

---

## 12. Build Plan (7 Days)

### Day 1 — Infrastructure Setup
- [ ] Create GitHub repository, clone locally
- [ ] Sign up for Databricks Free Edition, create workspace
- [x] Create Hive databases in a Databricks notebook: `CREATE DATABASE IF NOT EXISTS bronze/silver/gold`
- [ ] Create Google Cloud project, enable Sheets API, create Service Account, download JSON key
- [ ] Create the Google Sheet with 2 tabs matching schemas in §4.1 and §4.2
- [ ] Share the Google Sheet with the service account email address
- [ ] Add all 5 secrets to GitHub Secrets
- [ ] Create `ingestion/csv_uploads/` folder with `template.csv` and `.gitkeep`
- [ ] Run `ingestion/generate_dummy_data.py` to populate 6 months of test data

### Day 2 — Bronze Ingestion (Both Sources)
- [ ] Write `ingestion/ingest_bronze.py` (Google Sheets → Bronze, `_source = 'google_sheets'`)
- [ ] Write `ingestion/ingest_csv.py` (CSV → Bronze, `_source = 'csv_upload'`, moves to `processed/`)
- [ ] Test locally: verify `bronze.transactions` and `bronze.budgets` exist
- [ ] Test CSV path: drop a test CSV, run `ingest_csv.py`, verify rows tagged correctly
- [ ] Confirm `_ingested_at` and `_source` columns present on all rows

### Day 3 — dbt Setup + Silver Layer
- [ ] `pip install dbt-databricks`, run `dbt init wealth_flow_dbt`
- [ ] Configure `profiles.yml` using environment variables
- [ ] Create `seeds/fx_rates.csv` with EUR/USD/INR fixed rates
- [ ] Write `stg_transactions.sql` (dedup + FX join → `amount_eur`) and `stg_budgets.sql`
- [ ] Write `schema.yml` with all dbt tests
- [ ] `dbt seed && dbt run --select silver && dbt test --select silver` — all green

### Day 4 — Gold Layer
- [ ] Write all 4 gold models
- [ ] Add `schema.yml` tests for gold
- [ ] `dbt run --select gold`
- [ ] Spot-check in Databricks SQL editor: verify EUR amounts, subscription detection, budget variance logic

### Day 5 — GitHub Actions
- [ ] Write `pipeline.yml` (3-day scheduled run)
- [ ] Write `csv_ingest.yml` (triggered on CSV push to `csv_uploads/`)
- [ ] Write `ci.yml` (PR validation)
- [ ] Trigger a manual `workflow_dispatch` run — verify end-to-end succeeds in CI logs
- [ ] Test CSV trigger: commit a CSV to `csv_uploads/`, verify workflow fires

### Day 6 — Streamlit Dashboard
- [ ] Write `dashboard/app.py` with all 5 panels using Plotly charts
- [ ] Write `dashboard/requirements.txt`
- [ ] Test locally: `streamlit run dashboard/app.py`
- [ ] Deploy to Streamlit Community Cloud, add 3 secrets in the UI
- [ ] Verify public URL loads and all panels show data

### Day 7 — Validation & Polish
- [ ] Add 5–10 new rows to the Google Sheet, trigger pipeline, verify they appear in Streamlit
- [ ] Re-add 3 rows with duplicate `transaction_id` values, verify deduplication in Silver
- [ ] Verify FX conversion: add a USD and INR transaction, confirm `amount_eur` is correct
- [ ] Commit a fresh CSV via the repo, verify the CSV trigger workflow fires end-to-end
- [ ] Write `README.md` with: architecture diagram, setup instructions, link to live Streamlit dashboard

---

## 13. Assumptions & Constraints

- **Databricks Community Edition** is free forever. The workspace uses Unity Catalog with the `workspace` catalog. All table references are three-part `workspace.schema.table`. The lightweight pipeline stays well within Community Edition compute limits.
- **Fixed FX rates** mean amounts are not re-valued when rates change. This is intentional for a personal tracker — predictable and auditable. To update rates, edit `fx_rates.csv` and commit.
- The Google Sheet must be **shared with the service account email** (e.g. `wealth-flow@project-id.iam.gserviceaccount.com`) with at least Viewer access.
- `transaction_id` values must be unique and non-null in the source. A Google Apps Script to auto-generate UUIDs can be added post-MVP.
- **CSV uploads** must match the exact column headers in §4.1. The `template.csv` in the repo makes this clear. Invalid CSVs are rejected with an error, not silently skipped.
- **Streamlit Community Cloud** is free for public apps on a public GitHub repo. The Databricks credentials used by the dashboard are read-only (only querying Gold tables).
- All Gold-layer analysis is in EUR. Original `amount` and `currency` are preserved in Silver for auditability.
