"""
Local CSV ingestion UI. Not deployed to Streamlit Community Cloud.
Run with: streamlit run dashboard/ingest.py
"""

import re
from datetime import datetime, timezone

import pandas as pd
import streamlit as st
from databricks import sql as dbsql
from dotenv import load_dotenv
import os

load_dotenv()

REQUIRED_COLS = [
    "transaction_id", "date", "merchant", "amount",
    "currency", "type", "category", "account", "notes",
]
VALID_CURRENCIES = {"EUR", "USD", "INR"}
VALID_TYPES      = {"income", "expense"}
MAX_FILE_BYTES   = 10 * 1024 * 1024
CONTROL_RE       = re.compile(r"[\x00-\x1f\x7f]")

# ── page ──────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="Wealth-Flow — Ingest CSV", layout="centered")
st.title("CSV Ingestion")
st.caption(
    "Upload a CSV matching the template schema. Valid rows go to "
    "`workspace.bronze.transactions`. Run dbt afterwards to refresh Silver and Gold."
)

with st.expander("Required columns"):
    st.code(", ".join(REQUIRED_COLS))

# ── helpers ───────────────────────────────────────────────────────────────────

def _clean(val) -> str:
    return CONTROL_RE.sub("", str(val).strip())


def _validate_row(row: pd.Series, idx: int) -> str | None:
    if not _clean(row.get("transaction_id", "")):
        return f"Row {idx}: empty transaction_id"
    if _clean(row.get("currency", "")).upper() not in VALID_CURRENCIES:
        return f"Row {idx}: invalid currency '{row.get('currency')}'"
    if _clean(row.get("type", "")).lower() not in VALID_TYPES:
        return f"Row {idx}: invalid type '{row.get('type')}'"
    try:
        if float(row.get("amount", 0)) <= 0:
            raise ValueError
    except (ValueError, TypeError):
        return f"Row {idx}: invalid amount '{row.get('amount')}'"
    try:
        datetime.strptime(str(row.get("date", "")), "%Y-%m-%d")
    except ValueError:
        return f"Row {idx}: invalid date '{row.get('date')}'"
    return None


def _get_connection():
    host     = os.getenv("DATABRICKS_HOST", "")
    token    = os.getenv("DATABRICKS_TOKEN", "")
    http_path = os.getenv("DATABRICKS_HTTP_PATH", "")
    if not all([host, token, http_path]):
        st.error("DATABRICKS_HOST / DATABRICKS_TOKEN / DATABRICKS_HTTP_PATH not set. Source your .env file first.")
        st.stop()
    return dbsql.connect(server_hostname=host, http_path=http_path, access_token=token)


_BATCH_SIZE = 500
_ROW_PLACEHOLDER = "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"


def _build_params(row: dict, ingested_at: datetime) -> tuple:
    return (
        _clean(row["transaction_id"]),
        _clean(row["date"]),
        _clean(row["merchant"]),
        str(row["amount"]),
        _clean(row["currency"]).upper(),
        _clean(row["type"]).lower(),
        _clean(row.get("category", "")),
        _clean(row.get("account", "")),
        _clean(row.get("notes", "")),
        "csv_upload",
        ingested_at,
    )


def _insert_rows(rows: list[dict], ingested_at: datetime) -> None:
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS workspace.bronze.transactions (
                    transaction_id STRING, date STRING, merchant STRING,
                    amount STRING, currency STRING, type STRING,
                    category STRING, account STRING, notes STRING,
                    _source STRING, _ingested_at TIMESTAMP
                ) USING DELTA
            """)
            for i in range(0, len(rows), _BATCH_SIZE):
                batch = rows[i:i + _BATCH_SIZE]
                placeholders = ", ".join([_ROW_PLACEHOLDER] * len(batch))
                flat_params = [p for row in batch for p in _build_params(row, ingested_at)]
                cur.execute(
                    f"INSERT INTO workspace.bronze.transactions "
                    f"(transaction_id, date, merchant, amount, currency, type, "
                    f"category, account, notes, _source, _ingested_at) VALUES {placeholders}",
                    flat_params,
                )
    finally:
        conn.close()


# ── upload + validate ─────────────────────────────────────────────────────────

uploaded = st.file_uploader("Drop your CSV here", type=["csv"])

if uploaded is None:
    st.stop()

if uploaded.size > MAX_FILE_BYTES:
    st.error(f"File exceeds 10 MB limit ({uploaded.size / 1e6:.1f} MB). Rejected.")
    st.stop()

try:
    df = pd.read_csv(uploaded, dtype=str, encoding="utf-8", keep_default_na=False)
except Exception as exc:
    st.error(f"Could not parse CSV: {exc}")
    st.stop()

# Column check
missing = set(REQUIRED_COLS) - set(df.columns)
extra   = set(df.columns) - set(REQUIRED_COLS)

if missing:
    st.error(f"Missing required columns: `{sorted(missing)}`")
    st.stop()

if extra:
    st.warning(f"Extra columns ignored: `{sorted(extra)}`")

df = df[REQUIRED_COLS]

# Row validation
errors = []
valid_rows = []
for i, (_, row) in enumerate(df.iterrows(), start=2):
    err = _validate_row(row, i)
    if err:
        errors.append(err)
    else:
        valid_rows.append(row.to_dict())

# ── results ───────────────────────────────────────────────────────────────────

col1, col2 = st.columns(2)
col1.metric("Valid rows",   len(valid_rows))
col2.metric("Skipped rows", len(errors))

if errors:
    with st.expander(f"Validation issues ({len(errors)})"):
        for e in errors:
            st.warning(e)

if valid_rows:
    st.subheader("Preview (first 10 valid rows)")
    st.dataframe(pd.DataFrame(valid_rows).head(10), use_container_width=True, hide_index=True)

    st.divider()

    if st.button(f"Ingest {len(valid_rows)} rows into Bronze", type="primary"):
        with st.spinner("Writing to Databricks..."):
            try:
                _insert_rows(valid_rows, datetime.now(timezone.utc))
                st.success(
                    f"Done — {len(valid_rows)} rows written to `workspace.bronze.transactions`. "
                    "Run `dbt run --select silver gold` to refresh Silver and Gold."
                )
            except Exception as exc:
                st.error(f"Ingestion failed: {exc}")
else:
    st.error("No valid rows to ingest.")
