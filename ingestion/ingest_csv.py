"""
CSV files in csv_uploads/ → bronze.transactions (append).
Processed files are moved to csv_uploads/processed/ — never deleted.
"""

import logging
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from databricks import sql as dbsql
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ── constants ─────────────────────────────────────────────────────────────────

REQUIRED_COLS = [
    "transaction_id", "date", "merchant", "amount",
    "currency", "type", "category", "account", "notes",
]
VALID_CURRENCIES = {"EUR", "USD", "INR"}
VALID_TYPES = {"income", "expense"}
MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB
CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f]")


# ── validation ────────────────────────────────────────────────────────────────

def _clean_string(value) -> str:
    return CONTROL_CHAR_RE.sub("", str(value).strip())


def _validate_csv_columns(df: pd.DataFrame, filename: str) -> bool:
    actual = set(df.columns.tolist())
    required = set(REQUIRED_COLS)
    missing = required - actual
    extra = actual - required
    if missing:
        logger.error("File '%s' rejected: missing columns %s", filename, sorted(missing))
        return False
    if extra:
        logger.warning("File '%s' has extra columns %s — they will be ignored", filename, sorted(extra))
    return True


def _validate_row(row: pd.Series, row_num: int, filename: str) -> bool:
    tid = _clean_string(row.get("transaction_id", ""))
    if not tid:
        logger.warning("%s row %d: empty transaction_id — skipped", filename, row_num)
        return False
    if _clean_string(row.get("currency", "")).upper() not in VALID_CURRENCIES:
        logger.warning("%s row %d: invalid currency '%s' — skipped", filename, row_num, row.get("currency"))
        return False
    if _clean_string(row.get("type", "")).lower() not in VALID_TYPES:
        logger.warning("%s row %d: invalid type '%s' — skipped", filename, row_num, row.get("type"))
        return False
    try:
        amt = float(row.get("amount", 0))
        if amt <= 0:
            raise ValueError
    except (ValueError, TypeError):
        logger.warning("%s row %d: invalid amount '%s' — skipped", filename, row_num, row.get("amount"))
        return False
    try:
        datetime.strptime(str(row.get("date", "")), "%Y-%m-%d")
    except ValueError:
        logger.warning("%s row %d: invalid date '%s' — skipped", filename, row_num, row.get("date"))
        return False
    return True


# ── Databricks ────────────────────────────────────────────────────────────────

def _get_db_connection():
    host = os.getenv("DATABRICKS_HOST", "")
    token = os.getenv("DATABRICKS_TOKEN", "")
    http_path = os.getenv("DATABRICKS_HTTP_PATH", "")
    if not all([host, token, http_path]):
        raise EnvironmentError(
            "DATABRICKS_HOST, DATABRICKS_TOKEN, and DATABRICKS_HTTP_PATH must be set"
        )
    return dbsql.connect(server_hostname=host, http_path=http_path, access_token=token)


def _ensure_bronze_transactions(cursor) -> None:
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


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _append_rows(cursor, rows: list[dict], ingested_at: datetime) -> int:
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
                "csv_upload",
                ingested_at,
            ),
        )
    return len(rows)


# ── file processing ───────────────────────────────────────────────────────────

def _process_file(path: Path, cursor, ingested_at: datetime) -> bool:
    filename = path.name

    if path.stat().st_size > MAX_FILE_BYTES:
        logger.error("File '%s' rejected: exceeds 10 MB size limit", filename)
        return False

    try:
        df = pd.read_csv(path, dtype=str, encoding="utf-8", keep_default_na=False)
    except Exception as exc:
        logger.error("File '%s' could not be parsed: %s", filename, exc)
        return False

    if not _validate_csv_columns(df, filename):
        return False

    # Only keep the 9 required columns
    df = df[REQUIRED_COLS]

    valid_rows = []
    for i, (_, row) in enumerate(df.iterrows(), start=2):
        if _validate_row(row, i, filename):
            valid_rows.append(row.to_dict())

    logger.info(
        "File '%s': %d total rows, %d valid, %d skipped",
        filename, len(df), len(valid_rows), len(df) - len(valid_rows),
    )

    if valid_rows:
        written = _append_rows(cursor, valid_rows, ingested_at)
        logger.info("Appended %d rows from '%s'", written, filename)

    return True


def _move_to_processed(path: Path, processed_dir: Path) -> None:
    dest = processed_dir / path.name
    if dest.exists():
        # Avoid collision: append timestamp
        stem = path.stem
        suffix = path.suffix
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        dest = processed_dir / f"{stem}_{ts}{suffix}"
    shutil.move(str(path), str(dest))
    logger.info("Moved '%s' → processed/%s", path.name, dest.name)


# ── main ──────────────────────────────────────────────────────────────────────

def ingest() -> None:
    upload_dir = Path(os.getenv("CSV_UPLOADS_DIR", "ingestion/csv_uploads"))
    processed_dir = Path(os.getenv("CSV_PROCESSED_DIR", "ingestion/csv_uploads/processed"))
    processed_dir.mkdir(parents=True, exist_ok=True)

    csv_files = sorted(
        f for f in upload_dir.iterdir()
        if f.is_file() and f.suffix.lower() == ".csv" and f.name != "template.csv"
    )

    if not csv_files:
        logger.info("No CSV files found in %s — nothing to do", upload_dir)
        return

    logger.info("Found %d CSV file(s) to process", len(csv_files))
    ingested_at = datetime.now(timezone.utc)

    conn = _get_db_connection()
    try:
        with conn.cursor() as cursor:
            _ensure_bronze_transactions(cursor)
            for path in csv_files:
                success = _process_file(path, cursor, ingested_at)
                if success:
                    _move_to_processed(path, processed_dir)
                else:
                    logger.error("File '%s' was NOT moved — inspect and fix manually", path.name)
    finally:
        conn.close()

    logger.info("CSV ingestion complete")


if __name__ == "__main__":
    ingest()
