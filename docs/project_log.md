# Wealth-Flow Lakehouse — Project Log

> **Policy:** This document is updated only when a `git commit` is made.
> Each entry records the commit hash, date, what was achieved, and current project state.
> It is the single source of truth for "where is the project right now."

---

## Project Overview

**Name:** Wealth-Flow Lakehouse  
**Purpose:** Production-grade personal finance ELT pipeline demonstrating Medallion Architecture  
**Stack:** Google Sheets + CSV → Python ingestion → Databricks Delta Lake → dbt (Bronze/Silver/Gold) → Streamlit dashboard  
**Databricks tier:** Community Edition — Hive Metastore (two-part table names: `database.table`)  
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
| dbt Silver layer | ⬜ Not started | Day 3 task |
| dbt Gold layer | ⬜ Not started | Day 4 task |
| GitHub Actions workflows | ⬜ Not started | Day 5 task |
| Streamlit dashboard | ⬜ Not started | Day 6 task |
| End-to-end validation | ⬜ Not started | Day 7 task |

---

## Changelog

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
