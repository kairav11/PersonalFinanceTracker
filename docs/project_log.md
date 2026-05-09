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
| Bronze ingestion (Sheets) | ⬜ Not started | Day 2 task |
| Bronze ingestion (CSV) | ⬜ Not started | Day 2 task |
| dbt Silver layer | ⬜ Not started | Day 3 task |
| dbt Gold layer | ⬜ Not started | Day 4 task |
| GitHub Actions workflows | ⬜ Not started | Day 5 task |
| Streamlit dashboard | ⬜ Not started | Day 6 task |
| End-to-end validation | ⬜ Not started | Day 7 task |

---

## Changelog

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
