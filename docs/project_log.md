# Wealth-Flow Lakehouse — Project Log

> **Policy:** This document is updated only when a `git commit` is made.
> Each entry records the commit hash, date, what was achieved, and current project state.
> It is the single source of truth for "where is the project right now."

---

## Project Overview

**Name:** Wealth-Flow Lakehouse  
**Purpose:** Production-grade personal finance ELT pipeline demonstrating Medallion Architecture  
**Stack:** Google Sheets + CSV → Python ingestion → Databricks Delta Lake → dbt (Bronze/Silver/Gold) → Streamlit dashboard  
**Databricks tier:** Community Edition — Unity Catalog (`workspace` catalog; three-part table names: `workspace.schema.table`)  
**Base currency:** EUR (fixed FX: USD 0.926, INR 0.011)  
**Hosted dashboard:** Streamlit Community Cloud (public URL — recruiter-facing)  
**Orchestration:** GitHub Actions (every 3 days + CSV push trigger)

Full architecture: `project_plan.md`  
Full specification: `project_spec.md`

---

## Current Status

| Component | Status | Notes |
|---|---|---|
| Project planning | ✅ Complete | `project_plan.md` finalised |
| Specification | ✅ Complete | `project_spec.md` finalised |
| CLAUDE.md | ✅ Complete | Security constraints + best practices included |
| `.env` template | ✅ Complete | All env vars defined, no real secrets |
| Infrastructure (Databricks) | ✅ Complete | Community Edition workspace + Hive DBs created |
| Infrastructure (Google Cloud) | ✅ Complete | Service Account + Sheets API + Google Sheet created |
| `.gitignore` | ✅ Complete | Covers credentials, Python, dbt artefacts |
| Bronze ingestion (Sheets) | ✅ Complete | |
| Bronze ingestion (CSV) | ✅ Complete | |
| dbt Silver layer | ✅ Complete | |
| dbt Gold layer | ✅ Complete | |
| GitHub Actions workflows | ✅ Complete | |
| Streamlit dashboard | ⬜ Not started | Day 6 task |
| End-to-end validation | ⬜ Not started | Day 7 task |

---

## Changelog

### [v0.5] — 2026-05-09 — GitHub Actions workflows live
**Commit:** pending  
**Branch:** `feature/github-actions`

**Achieved:**
- `pipeline.yml`: full pipeline on 3-day cron + manual dispatch — Sheets ingest → seed → Silver run → Silver test (--fail-fast) → Gold run
- `csv_ingest.yml`: triggered on push to `csv_uploads/*.csv` — CSV ingest → Silver → test → Gold
- `ci.yml`: runs on every PR — `dbt compile` + `dbt test --select silver --fail-fast` to block broken models from merging
- All workflows: `permissions: contents: read`, Actions pinned to commit SHA, secrets referenced via `${{ secrets.NAME }}` only, no `set -x`

**Files changed:**
```
.github/workflows/pipeline.yml    (created)
.github/workflows/csv_ingest.yml  (created)
.github/workflows/ci.yml          (created)
docs/project_log.md               (updated)
```

**Known issues / follow-ups:**
- `actions/setup-python` SHA should be verified against the latest v5 release tag before merging
- CSV file moves (`processed/`) do not persist in CI since the runner is ephemeral — data integrity maintained by Silver deduplication on `transaction_id`

**Updated status table rows:**
| Component | Old status | New status |
|---|---|---|
| GitHub Actions workflows | ⬜ Not started | ✅ Complete |



### [v0.4] — 2026-05-09 — dbt Gold layer complete
**Commit:** pending  
**Branch:** `feature/gold-dbt`

**Achieved:**
- `fct_monthly_burn`: monthly totals by category + type in EUR, with YTD running total partitioned by calendar year
- `fct_income_vs_expense`: monthly income vs expense with net cash flow and 3-month rolling average
- `fct_budget_variance`: actual spend vs configured budget per category per month; computes variance_eur, variance_pct, over_budget flag; nulls where no budget is set
- `dim_subscription_tracker`: detects recurring merchants (≥3 distinct months, charges within ±2% of median); outputs estimated monthly cost, first/last seen, occurrence count
- `gold/schema.yml`: tests on all Gold models — all passing

**Files changed:**
```
wealth_flow_dbt/models/gold/fct_monthly_burn.sql         (created)
wealth_flow_dbt/models/gold/fct_income_vs_expense.sql    (created)
wealth_flow_dbt/models/gold/fct_budget_variance.sql      (created)
wealth_flow_dbt/models/gold/dim_subscription_tracker.sql (created)
wealth_flow_dbt/models/gold/schema.yml                   (created)
docs/project_log.md                                      (updated)
```

**Known issues / follow-ups:**
- None — all Gold tests passing

**Updated status table rows:**
| Component | Old status | New status |
|---|---|---|
| dbt Gold layer | ⬜ Not started | ✅ Complete |



### [v0.3] — 2026-05-09 — dbt Silver layer complete + Unity Catalog migration
**Commit:** pending  
**Branch:** `feature/silver-dbt`

**Achieved:**
- Built full dbt project structure: `dbt_project.yml`, `profiles.yml`, `packages.yml`, `macros/`, `seeds/`, `models/`
- `seeds/fx_rates.csv`: fixed FX rates (EUR=1.0, USD=0.926, INR=0.011) loaded into `workspace.silver.fx_rates`
- `macros/generate_schema_name.sql`: overrides dbt default so custom schemas are used as-is (e.g. `silver`, not `silver_silver`)
- `models/sources.yml`: declares `workspace.bronze.transactions` and `workspace.bronze.budgets` as dbt sources
- `silver/stg_transactions.sql`: deduplication (latest `_ingested_at` wins), type casting, string cleaning, FX join → `amount_eur`
- `silver/stg_budgets.sql`: casts `monthly_budget_eur` to DECIMAL, filters nulls
- `silver/schema.yml`: 19 tests — unique, not_null, accepted_values, expression_is_true — all passing
- **Unity Catalog discovery**: workspace uses UC (`workspace` catalog), not Hive Metastore. Fixed `profiles.yml` (`catalog: workspace`), `sources.yml`, and both ingestion scripts (three-part table names). All docs updated.
- Fixed `dbt_utils.expression_is_true` syntax: expression must be operator-only (e.g. `> 0`), not include the column name.

**Files changed:**
```
wealth_flow_dbt/dbt_project.yml              (created)
wealth_flow_dbt/profiles.yml                 (created)
wealth_flow_dbt/packages.yml                 (created)
wealth_flow_dbt/seeds/fx_rates.csv           (created)
wealth_flow_dbt/macros/generate_schema_name.sql (created)
wealth_flow_dbt/models/sources.yml           (created)
wealth_flow_dbt/models/silver/stg_transactions.sql (created)
wealth_flow_dbt/models/silver/stg_budgets.sql (created)
wealth_flow_dbt/models/silver/schema.yml     (created)
ingestion/ingest_bronze.py                   (updated — three-part table names)
ingestion/ingest_csv.py                      (updated — three-part table names)
project_plan.md                              (updated — UC throughout)
project_spec.md                              (updated — §5.3 UC naming)
CLAUDE.md                                    (updated — UC in dbt section + decisions table)
docs/project_log.md                          (this file)
```

**Known issues / follow-ups:**
- `dbt_packages/` (created by `dbt deps`) must not be committed — confirm it is in `.gitignore`
- Gold layer (`workspace.gold.*`) schemas do not exist yet — created in Day 4

**Updated status table rows:**
| Component | Old status | New status |
|---|---|---|
| dbt Silver layer | ⬜ Not started | ✅ Complete |



### [v0.2] — 2026-05-09 — Bronze ingestion complete
**Commit:** pending  
**Branch:** `feature/bronze-ingestion`

**Achieved:**
- `ingest_bronze.py`: reads Transactions + Budgets tabs from Google Sheet, validates all rows, appends to `bronze.transactions` (append-only), overwrites `bronze.budgets` (full refresh). Parameterized SQL throughout — no f-strings. 3-retry exponential backoff on Sheets and Databricks calls.
- `ingest_csv.py`: processes all `.csv` files in `csv_uploads/`, validates columns and rows, rejects files > 10 MB, moves processed files to `csv_uploads/processed/` (never deletes). `template.csv` is always skipped.
- `generate_dummy_data.py`: generates 6 months of realistic dummy transactions (salary, freelance, interest income + 9 expense categories) and pushes to Google Sheet. Run once to seed the Sheet before first pipeline run.
- `requirements.txt`: all 7 dependencies pinned to exact versions.
- End-to-end verified: 140 rows confirmed in `bronze.transactions`, 9 rows in `bronze.budgets`. All currency/type checks pass, no nulls on required columns.

**Files changed:**
```
ingestion/ingest_bronze.py      (created)
ingestion/ingest_csv.py         (created)
ingestion/generate_dummy_data.py (created)
ingestion/requirements.txt      (created)
docs/project_log.md             (updated)
```

**Known issues / follow-ups:**
- `generate_dummy_data.py` requires write scope on the service account (`spreadsheets` + `drive.file`). The production service account only has `spreadsheets.readonly` — grant Editor on the Sheet manually when running this script, then revert to Viewer.
- Databricks SQL Warehouse cold start adds 2–4 min to first run of the day; subsequent runs are fast.
- Row-by-row INSERTs are fine at current data volume; revisit if ingestion grows beyond ~10k rows/run.

**Updated status table rows:**
| Component | Old status | New status |
|---|---|---|
| Bronze ingestion (Sheets) | ⬜ Not started | ✅ Complete |
| Bronze ingestion (CSV) | ⬜ Not started | ✅ Complete |



### [v0.1] — 2026-05-09 — Infrastructure setup + project foundation
**Commit:** pending first push  
**Branch:** `main`

**Achieved:**
- Chose **Databricks Community Edition** (Hive Metastore) over trial — free forever, no Unity Catalog
- All table references updated to two-part `database.table` naming throughout all docs
- Databricks workspace live; `bronze`, `silver`, `gold` Hive databases created via notebook
- Google Cloud project created (`wealth-flow-495800`), Sheets API enabled, Service Account created
- Google Sheet created (`Wealth-Flow Tracker`) with `Transactions` + `Budgets` tabs and correct headers
- Sheet shared with service account; all 5 GitHub Secrets added
- `.gitignore` hardened: covers `.env`, `service_account.json`, Python/dbt artefacts
- **Security incident:** original service account key was briefly exposed in IDE; key was rotated immediately, new key in place
- All planning docs (`project_plan.md`, `project_spec.md`, `CLAUDE.md`) updated to reflect Community Edition

**Files created/modified:**
```
.gitignore          (created — comprehensive)
.env                (updated — removed DATABRICKS_CATALOG, updated comment)
project_plan.md     (updated — Unity Catalog → Hive Metastore throughout)
project_spec.md     (updated — table names, §5.3 Databricks connection)
CLAUDE.md           (updated — dbt catalog note, security constraint, decisions table)
docs/project_log.md (this file — updated status table + changelog)
```

**Known issues / follow-ups:**
- `ingestion/service_account.json` must be replaced with the newly rotated key before running any ingestion script
- GitHub Secrets `GOOGLE_SERVICE_ACCOUNT_JSON` must also be updated with the new rotated key JSON

**Updated status table rows:**
| Component | Old status | New status |
|---|---|---|
| Infrastructure (Databricks) | ⬜ Not started | ✅ Complete |
| Infrastructure (Google Cloud) | ⬜ Not started | ✅ Complete |
| `.gitignore` | ⬜ Not started | ✅ Complete |

### [PLANNING] — 2026-05-09 — Pre-commit baseline
**Planning phase complete — superseded by v0.1 above.**

**Achieved:**
- Defined full project architecture (Medallion: Bronze / Silver / Gold)
- Finalised tech stack, all key design decisions resolved
- Created `project_plan.md`, `project_spec.md`, `CLAUDE.md`, `.env`, `docs/project_log.md`

---

<!--
TEMPLATE — copy this block and fill it in after each commit:

### [vX.Y] — YYYY-MM-DD — <short description>
**Commit:** `<short hash>`  
**Branch:** `<branch name>`

**Achieved:**
- <bullet: what was built or changed>

**Files changed:**
```
<list of files added/modified/deleted>
```

**Known issues / follow-ups:**
- <anything left incomplete or deferred>

**Updated status table rows:**
| Component | Old status | New status |
|---|---|---|
| <component> | ⬜ Not started | ✅ Complete |
-->
