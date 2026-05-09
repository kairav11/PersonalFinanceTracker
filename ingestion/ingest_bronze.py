"""
Google Sheets → bronze.transactions (append) + bronze.budgets (overwrite).
"""

import json
import logging
import os
import re
import time
from datetime import datetime, timezone

import gspread
import pandas as pd
from databricks import sql as dbsql
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from tenacity import retry, stop_after_attempt, wait_exponential

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ── constants ─────────────────────────────────────────────────────────────────

REQUIRED_TRANSACTION_COLS = {
    "transaction_id", "date", "merchant", "amount",
    "currency", "type", "category", "account", "notes",
}
VALID_CURRENCIES = {"EUR", "USD", "INR"}
VALID_TYPES = {"income", "expense"}
CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f]")


# ── credentials / clients ─────────────────────────────────────────────────────

def _get_gspread_client() -> gspread.Client:
    raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not raw:
        path = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_PATH", "")
        if not path or not os.path.exists(path):
            raise EnvironmentError(
                "Set GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_SERVICE_ACCOUNT_JSON_PATH"
            )
        with open(path) as f:
            raw = f.read()
    key_data = json.loads(raw)
    scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    creds = Credentials.from_service_account_info(key_data, scopes=scopes)
    return gspread.authorize(creds)


def _get_db_connection():
    host = os.getenv("DATABRICKS_HOST", "")
    token = os.getenv("DATABRICKS_TOKEN", "")
    http_path = os.getenv("DATABRICKS_HTTP_PATH", "")
    if not all([host, token, http_path]):
        raise EnvironmentError(
            "DATABRICKS_HOST, DATABRICKS_TOKEN, and DATABRICKS_HTTP_PATH must be set"
        )
    return dbsql.connect(server_hostname=host, http_path=http_path, access_token=token)


# ── input validation ──────────────────────────────────────────────────────────

def _clean_string(value: str) -> str:
    return CONTROL_CHAR_RE.sub("", str(value).strip())


def _validate_transaction_row(row: dict, row_num: int) -> bool:
    tid = row.get("transaction_id", "").strip()
    if not tid:
        logger.warning("Row %d: empty transaction_id — skipped", row_num)
        return False
    if row.get("currency", "").strip().upper() not in VALID_CURRENCIES:
        logger.warning("Row %d (id=%s): invalid currency '%s' — skipped", row_num, tid, row.get("currency"))
        return False
    if row.get("type", "").strip().lower() not in VALID_TYPES:
        logger.warning("Row %d (id=%s): invalid type '%s' — skipped", row_num, tid, row.get("type"))
        return False
    try:
        amt = float(row.get("amount", "0"))
        if amt <= 0:
            raise ValueError
    except (ValueError, TypeError):
        logger.warning("Row %d (id=%s): invalid amount '%s' — skipped", row_num, tid, row.get("amount"))
        return False
    try:
        datetime.strptime(row.get("date", ""), "%Y-%m-%d")
    except ValueError:
        logger.warning("Row %d (id=%s): invalid date '%s' — skipped", row_num, tid, row.get("date"))
        return False
    return True


# ── Google Sheets helpers ─────────────────────────────────────────────────────

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _fetch_sheet_tab(client: gspread.Client, sheet_id: str, tab_name: str) -> list[dict]:
    sheet = client.open_by_key(sheet_id)
    ws = sheet.worksheet(tab_name)
    return ws.get_all_records(head=1)


# ── Databricks write helpers ──────────────────────────────────────────────────

def _ensure_bronze_tables(cursor) -> None:
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bronze.transactions (
            transaction_id STRING,
            date           STRING,
            merchant       STRING,
            amount         STRING,
            currency       STRING,
            type           STRING,
            category       STRING,
            account        STRING,
            notes          STRING,
            _source        STRING,
            _ingested_at   TIMESTAMP
        ) USING DELTA
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bronze.budgets (
            category           STRING,
            monthly_budget_eur STRING,
            _ingested_at       TIMESTAMP
        ) USING DELTA
    """)
    logger.info("Bronze tables confirmed to exist")


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _append_transactions(cursor, rows: list[dict], ingested_at: datetime) -> None:
    if not rows:
        logger.info("No transaction rows to append")
        return
    for row in rows:
        cursor.execute(
            """
            INSERT INTO bronze.transactions
                (transaction_id, date, merchant, amount, currency, type,
                 category, account, notes, _source, _ingested_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _clean_string(row["transaction_id"]),
                _clean_string(row["date"]),
                _clean_string(row["merchant"]),
                str(row["amount"]),
                _clean_string(row["currency"]).upper(),
                _clean_string(row["type"]).lower(),
                _clean_string(row.get("category", "")),
                _clean_string(row.get("account", "")),
                _clean_string(row.get("notes", "")),
                "google_sheets",
                ingested_at,
            ),
        )
    logger.info("Appended %d transaction rows from Google Sheets", len(rows))


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _overwrite_budgets(cursor, rows: list[dict], ingested_at: datetime) -> None:
    cursor.execute("DELETE FROM bronze.budgets")
    if not rows:
        logger.info("No budget rows to write")
        return
    for row in rows:
        cursor.execute(
            """
            INSERT INTO bronze.budgets (category, monthly_budget_eur, _ingested_at)
            VALUES (?, ?, ?)
            """,
            (
                _clean_string(row.get("category", "")),
                str(row.get("monthly_budget_eur", "")),
                ingested_at,
            ),
        )
    logger.info("Wrote %d budget rows", len(rows))


# ── main ──────────────────────────────────────────────────────────────────────

def ingest() -> None:
    sheet_id = os.getenv("GOOGLE_SHEET_ID", "")
    tx_tab = os.getenv("GOOGLE_TRANSACTIONS_TAB", "Transactions")
    budget_tab = os.getenv("GOOGLE_BUDGETS_TAB", "Budgets")
    if not sheet_id:
        raise EnvironmentError("GOOGLE_SHEET_ID must be set")

    ingested_at = datetime.now(timezone.utc)

    logger.info("Fetching Google Sheets data")
    gc = _get_gspread_client()
    raw_transactions = _fetch_sheet_tab(gc, sheet_id, tx_tab)
    raw_budgets = _fetch_sheet_tab(gc, sheet_id, budget_tab)

    # Validate transaction column presence
    if raw_transactions:
        actual_cols = set(raw_transactions[0].keys())
        missing = REQUIRED_TRANSACTION_COLS - actual_cols
        if missing:
            raise ValueError(f"Transactions tab missing columns: {missing}")

    # Validate rows
    valid_transactions = [
        row for i, row in enumerate(raw_transactions, start=2)
        if _validate_transaction_row(row, i)
    ]
    logger.info(
        "Transactions: %d total, %d valid, %d skipped",
        len(raw_transactions),
        len(valid_transactions),
        len(raw_transactions) - len(valid_transactions),
    )

    logger.info("Connecting to Databricks")
    conn = _get_db_connection()
    try:
        with conn.cursor() as cursor:
            _ensure_bronze_tables(cursor)
            _append_transactions(cursor, valid_transactions, ingested_at)
            _overwrite_budgets(cursor, raw_budgets, ingested_at)
    finally:
        conn.close()

    logger.info("Sheets ingestion complete")


if __name__ == "__main__":
    ingest()
