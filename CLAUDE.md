# Wealth-Flow Lakehouse — Claude Code Guide

## What this project is

A personal finance ELT pipeline: Google Sheets + CSV → Databricks Delta Lake (Medallion Architecture via dbt) → public Streamlit dashboard. Full spec in `project_spec.md`. Timeline in `project_plan.md`.

---

## Repo Layout

```
.
├── ingestion/
│   ├── ingest_bronze.py          # Google Sheets → bronze.transactions + bronze.budgets
│   ├── ingest_csv.py             # csv_uploads/*.csv → bronze.transactions
│   ├── generate_dummy_data.py    # Populates Google Sheet with 6 months of test data
│   ├── requirements.txt
│   └── csv_uploads/
│       ├── template.csv          # Schema reference — do not delete
│       └── processed/            # Ingested CSVs are moved here, never deleted
├── wealth_flow_dbt/
│   ├── dbt_project.yml
│   ├── profiles.yml              # Reads from env vars — no hardcoded credentials
│   ├── seeds/fx_rates.csv        # Fixed FX rates: EUR(1.0) / USD(0.926) / INR(0.011)
│   └── models/
│       ├── silver/               # stg_transactions, stg_budgets
│       └── gold/                 # fct_monthly_burn, fct_budget_variance,
│                                 # fct_income_vs_expense, dim_subscription_tracker
├── dashboard/
│   ├── app.py                    # Streamlit app — reads Gold tables only
│   ├── requirements.txt
│   └── .streamlit/secrets.toml.example
├── .github/workflows/
│   ├── pipeline.yml              # Runs every 3 days + manual dispatch
│   ├── csv_ingest.yml            # Triggers on push to csv_uploads/*.csv
│   └── ci.yml                    # Runs on every PR
├── .env                          # Local secrets — never commit
├── project_plan.md               # Architecture + 7-day build plan
└── project_spec.md               # Functional requirements, data contracts, acceptance criteria
```

---

## Environment Setup

```bash
# Copy env template and fill in real values
cp .env .env.local   # never commit .env with real values

# Install ingestion dependencies
pip install -r ingestion/requirements.txt

# Install dbt
pip install dbt-databricks

# Install dashboard dependencies
pip install -r dashboard/requirements.txt

# Load env vars before running any script locally
source .env
```

---

## Common Commands

### Ingestion
```bash
# Ingest from Google Sheets
python ingestion/ingest_bronze.py

# Ingest from CSV files in csv_uploads/
python ingestion/ingest_csv.py

# Generate and push 6 months of dummy data to the Sheet
python ingestion/generate_dummy_data.py
```

### dbt
```bash
cd wealth_flow_dbt

# First-time: load seed data
dbt seed

# Run Silver only (always run seed first)
dbt run --select silver

# Test Silver (must pass before running Gold)
dbt test --select silver

# Run Gold
dbt run --select gold

# Full pipeline (seed → silver → test → gold)
dbt seed && dbt run --select silver && dbt test --select silver && dbt run --select gold

# Check for syntax errors without running
dbt compile

# Rebuild everything from scratch
dbt seed && dbt run --full-refresh
```

### Dashboard
```bash
# Run locally
streamlit run dashboard/app.py
```

---

## Architecture Rules — Read Before Changing Anything

### Bronze layer
- `bronze.transactions` is **append-only**. Never use overwrite/truncate on this table.
- `bronze.budgets` is **full-overwrite** on every run. This is intentional — budgets change infrequently.
- Every row in `bronze.transactions` must have `_source` (`'google_sheets'` or `'csv_upload'`) and `_ingested_at`.
- Bronze stores **raw strings only** — no type casting here.

### Deduplication
- Dedup key: `transaction_id` (case-sensitive string match).
- When duplicates exist, keep the row with the **latest `_ingested_at`**.
- Dedup is enforced in `stg_transactions.sql`, not in the ingestion scripts.

### FX / Currency
- Base reporting currency is **EUR**. All Gold columns are `*_eur`.
- Rates live in `seeds/fx_rates.csv`. **Do not add a live API call** — fixed rates are intentional for auditability.
- Supported currencies: `EUR`, `USD`, `INR` only. Any other value will fail the dbt `accepted_values` test.
- Silver adds `amount_eur = amount * rate_to_eur`. Original `amount` and `currency` are kept.

### dbt model materialization
- All Silver and Gold models use `table` materialization (full refresh each run). **Do not switch to incremental** — not needed at this data volume and adds complexity.
- Run order is enforced by `ref()` — don't use hardcoded table names.

### dbt tests
- Silver tests **must all pass** before Gold runs. The CI workflow and `pipeline.yml` enforce this with sequential steps.
- If you add a new Silver column, add a test for it in `silver/schema.yml`.

### CSV ingestion
- All 9 columns from §4.1 of `project_spec.md` are required. Missing columns → file is rejected with a logged error, not silently skipped.
- Processed CSVs are **moved to `csv_uploads/processed/`**, never deleted.
- `template.csv` must always reflect the current schema — update it if the schema changes.

### Dashboard
- `app.py` reads **Gold tables only** — never query Bronze or Silver from the dashboard.
- All Databricks queries must be wrapped with `@st.cache_data(ttl=3600)`.
- Empty Gold tables must show `st.info("No data available yet.")`, not raise an exception.

---

## GitHub Actions

| Workflow | Trigger | What it does |
|---|---|---|
| `pipeline.yml` | Every 3 days (`0 0 */3 * *`) + `workflow_dispatch` | Full pipeline: ingest → seed → silver → test → gold |
| `csv_ingest.yml` | Push to `ingestion/csv_uploads/*.csv` | CSV ingest → silver → gold |
| `ci.yml` | Every PR | `dbt compile` + `dbt test --select silver` |

### Required GitHub Secrets
```
DATABRICKS_HOST
DATABRICKS_TOKEN
DATABRICKS_HTTP_PATH
GOOGLE_SERVICE_ACCOUNT_JSON   # full JSON content, not a file path
GOOGLE_SHEET_ID
```

---

## Data Contracts (quick reference)

Full contracts with types and nullability are in `project_spec.md §4`.

| Table | Grain | Key column(s) |
|---|---|---|
| `bronze.transactions` | One row per ingested record (may have dupes) | `transaction_id` (not enforced unique) |
| `silver.stg_transactions` | One row per unique transaction | `transaction_id` (unique) |
| `silver.stg_budgets` | One row per category | `category` (unique) |
| `gold.fct_monthly_burn` | `(year_month, category, type)` | — |
| `gold.fct_budget_variance` | `(year_month, category)` | — |
| `gold.fct_income_vs_expense` | `year_month` | — |
| `gold.dim_subscription_tracker` | `merchant` | — |

---

## Subscription Detection Logic

A merchant qualifies as a recurring subscription when:
1. The same `merchant` string appears in **≥ 3 distinct calendar months**
2. The `amount_eur` values are within **±2% of the merchant's median charge**

This logic lives entirely in `gold/dim_subscription_tracker.sql`.

---

## What NOT to Do

- Do not commit `.env` or `service_account.json` — they contain real credentials.
- Do not hardcode Databricks credentials anywhere in Python or SQL files.
- Do not modify `seeds/fx_rates.csv` rates without explicit instruction — they are intentionally fixed.
- Do not add a `bronze.exchange_rates` table — the live API approach was explicitly rejected.
- Do not use `dbt run --select gold` without running Silver tests first.
- Do not rename the Google Sheet tabs without updating `GOOGLE_TRANSACTIONS_TAB` / `GOOGLE_BUDGETS_TAB` env vars.
- Do not add incremental materialization to any model without discussing first.
- Do not push to `main` if `ci.yml` is failing.
- Do not use `git add .` or `git add -A` — always stage files explicitly by name.
- Do not use `set -x` in any GitHub Actions step — it prints all env vars including secrets to logs.
- Do not pass secrets as CLI arguments — they appear in process lists and logs.
- Do not use bare `except:` in Python — always catch specific exception types.
- Do not use `print()` in any ingestion or pipeline script — use the `logging` module.

---

## Security Constraints

These are non-negotiable. Raise them with the user before proceeding if any change risks violating them.

### Credential Handling
- All secrets must be read from environment variables (`os.getenv()`). No fallback values that resemble real credentials (e.g. `os.getenv("TOKEN", "dapi123")` is forbidden).
- `service_account.json` must never exist anywhere except the local machine and GitHub Secrets. It must appear in `.gitignore` before the first `git push`.
- The Google Service Account must be granted **only** `spreadsheets.readonly` scope — no broader Google API access.
- The Databricks Personal Access Token used by the dashboard must have **only** SELECT access on `gold.*`. It should not be the same token used for ingestion (which writes to Bronze).
- If a secret is accidentally logged or committed: rotate it immediately before doing anything else.

### SQL Safety
- Never build SQL strings using f-strings or `.format()` with values derived from CSV rows, Sheet data, or any external input. Use parameterized queries via the `databricks-sql-connector` cursor (i.e., pass parameters as the second arg to `.execute()`).
- The Streamlit dashboard must only execute `SELECT` statements. No DDL (`CREATE`, `DROP`, `ALTER`) or DML (`INSERT`, `UPDATE`, `DELETE`) from `app.py` under any circumstances.
- dbt models use only `{{ ref() }}` and `{{ source() }}` — never interpolate Python variables into `.sql` files.

### Input Validation (CSV & Sheets)
All ingested data must be validated **before** writing to Bronze. Reject the row (log + skip) if:
- `currency` is not one of `EUR`, `USD`, `INR`
- `type` is not one of `income`, `expense`
- `amount` cannot be parsed as a positive decimal
- `date` cannot be parsed as `YYYY-MM-DD`
- `transaction_id` is empty or null

Strip leading/trailing whitespace and control characters from all string fields (`merchant`, `notes`, `category`, `account`) before writing.

Cap CSV file size at **10 MB**. Reject with a clear error if exceeded.

### What Must Be in `.gitignore`
Verify this file exists and contains all of the following before the first push:
```
.env
*.env
ingestion/service_account.json
ingestion/*.json
.streamlit/secrets.toml
__pycache__/
*.pyc
*.pyo
.DS_Store
```

### GitHub Actions Hardening
- All workflows must declare `permissions: contents: read` at the top level and only elevate where strictly necessary.
- Pin third-party Actions to a full commit SHA, not a mutable tag:
  ```yaml
  # Bad  — tag can be moved maliciously
  uses: actions/checkout@v4
  # Good — SHA is immutable
  uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683
  ```
- Secrets are referenced as `${{ secrets.NAME }}` only — never echoed, never written to a file in the workflow.
- Add `continue-on-error: false` (the default) to all pipeline steps — a silent failure is worse than a loud one.

---

## Security Checks — Run Before These Actions

### Before the first `git push` (one-time setup)
```bash
# 1. Verify .gitignore covers all sensitive files
cat .gitignore

# 2. Confirm no secrets are staged
git diff --staged

# 3. Confirm service_account.json is not tracked
git ls-files ingestion/*.json   # should return nothing

# 4. Scan git history for accidental secret commits
git log --all --full-history -- .env
git log --all --full-history -- "*.json"
```

### Before every commit
```bash
# Check staged files — no .env, no JSON keys, no tokens
git diff --staged --name-only

# Grep staged Python files for hardcoded token patterns
git diff --staged | grep -E "(dapi[a-zA-Z0-9]{32}|AIza[0-9A-Za-z_-]{35})"
# If this returns anything, do NOT commit.
```

### Before merging any PR that touches ingestion scripts or workflows
- Verify no new `print()` calls were added (use `logging` instead)
- Verify no new hardcoded strings that look like tokens, keys, or IDs
- Verify `requirements.txt` has pinned versions for any new packages added
- Verify GitHub Actions steps do not echo secrets

### Before deploying the Streamlit dashboard
- Confirm the Databricks token used in Streamlit secrets is a **separate, read-only token** scoped to Gold tables only
- Confirm `app.py` contains no write operations against Databricks
- Confirm `.streamlit/secrets.toml` is in `.gitignore` and not committed

---

## Code Quality & Best Practices

### Python
- Use `python-dotenv` (`load_dotenv()`) at the top of every script for local dev. CI uses real env vars injected by GitHub Actions — `load_dotenv()` is a no-op in that context.
- **Pin all package versions** in `requirements.txt`. Never use `gspread` — always `gspread==6.1.2`. Run `pip freeze > requirements.txt` after installing.
- Use `logging.getLogger(__name__)` in every module. Set level to `INFO` by default.
- **Never log financial amounts or merchant names at INFO/DEBUG level in CI** — these are personal data and will appear in public GitHub Actions logs. Log counts and row IDs only.
- Retry transient network errors (Google Sheets API, Databricks connection) with exponential backoff — max 3 retries.
- All ingestion functions must be **idempotent**: running them twice should produce the same Bronze state as running once (Bronze is append-only, so dedup in Silver handles the rest).

### dbt
- Every model must have a `description:` field in its `schema.yml` entry.
- No catalog prefix needed — Hive Metastore uses two-part names (`database.table`). Do not set `catalog` in `dbt_project.yml`.
- Run `dbt compile` before `dbt run` when editing models — catches Jinja/SQL errors without consuming compute.
- Add `--fail-fast` in CI `dbt test` runs so the first failure stops immediately rather than running all tests.
- Keep model SQL readable: one CTE per logical step, named descriptively.

### Git Hygiene
- Branch naming: `feature/`, `fix/`, `chore/` prefixes (e.g. `feature/csv-ingestion`).
- Commit messages: imperative mood, present tense (`add CSV ingestion`, not `added CSV ingestion`).
- Never commit directly to `main` — always open a PR, even for solo work.
- Squash trivial fixup commits before merging.
- Tag releases after each successful Day N milestone (e.g. `v0.2-silver-complete`).

---

## Documentation Policy

### Rule: Update `docs/project_log.md` after every commit — no exceptions.

`docs/project_log.md` is the single source of truth for the current state of the project. It must never fall behind the actual codebase.

### What to update after each commit

1. **Add a new changelog entry** at the top of the Changelog section using this exact template:
   ```
   ### [vX.Y] — YYYY-MM-DD — <short description>
   **Commit:** `<short hash from git log>`
   **Branch:** `<branch name>`

   **Achieved:**
   - <bullet per meaningful change>

   **Files changed:**
   <list of added/modified/deleted files>

   **Known issues / follow-ups:**
   - <anything deferred or left incomplete>

   **Updated status table rows:**
   | Component | Old status | New status |
   ```

2. **Update the Current Status table** — flip any newly completed rows from `⬜ Not started` or `🔄 In progress` to `✅ Complete`. Use `🔄 In progress` for partially done work.

3. **Do not edit previous changelog entries** — they are an immutable record. Corrections go in the new entry.

### Status icon key
| Icon | Meaning |
|---|---|
| ⬜ | Not started |
| 🔄 | In progress |
| ✅ | Complete |
| ❌ | Blocked / abandoned |

### What does NOT trigger a `docs/project_log.md` update
- Edits to `project_plan.md`, `project_spec.md`, or `CLAUDE.md` alone (planning docs, not code)
- Amending a commit (the original entry stands; note the amend in a follow-up entry only if behaviour changed)
- Commits that only update `docs/project_log.md` itself

### Version numbering convention
- `v0.1` — repo initialised, `.gitignore`, base file structure
- `v0.2` — Bronze ingestion working end-to-end
- `v0.3` — Silver layer passing all dbt tests
- `v0.4` — Gold layer complete
- `v0.5` — GitHub Actions workflows live
- `v0.6` — Streamlit dashboard deployed with public URL
- `v1.0` — full end-to-end validation passed (Day 7 checklist complete)

### Dependency Management
- Maintain separate `requirements.txt` files for `ingestion/` and `dashboard/` — they have different dependencies.
- After any `pip install`, regenerate with `pip freeze | grep -v "^-e" > requirements.txt` scoped to the active venv.
- Audit new packages before adding: check PyPI download count, last release date, and whether it's maintained.

### Databricks Free Tier — Staying Within Limits
- Use **Serverless SQL Warehouse** only — not all-purpose clusters (much cheaper, spins down in 10 min of inactivity).
- Keep individual dbt models simple: avoid cross-joins and window functions over the full Bronze table.
- If a pipeline run exceeds 5 minutes, profile it with `dbt --debug run` before optimising.

---

## Testing Checklist (Day 7)

See `project_spec.md §9` for the full manual validation checklist, including specific EUR conversion assertions (e.g. 100 USD → 92.60 EUR).

---

## Key Decisions Already Made

These were resolved during planning — do not re-open without good reason:

| Decision | Choice | Why |
|---|---|---|
| FX rates | Fixed seed, not live API | Auditable, no rate-limit risk, simpler |
| Base currency | EUR | User preference |
| Dedup strategy | Latest `_ingested_at` wins | Idempotent re-ingestion |
| Budget source | Google Sheets tab 2 | Avoids dbt seed churn when budgets change |
| Visualization | Streamlit Community Cloud | Free public URL for recruiter sharing |
| Materialization | Full refresh tables | Correct and simple at this data volume |
| Auth | Service Account (not OAuth) | Works headlessly in CI |
| Databricks tier | Community Edition (Hive Metastore) | Free forever; no Unity Catalog; two-part table names |
