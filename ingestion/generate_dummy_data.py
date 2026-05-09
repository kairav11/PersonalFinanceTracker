"""
Generates 6 months of realistic dummy transaction + budget data
and writes it directly to the configured Google Sheet.

Run once to populate the sheet before the first pipeline run.
Clears the sheet first — safe to re-run (idempotent).
"""

import json
import logging
import os
import random
from datetime import date, timedelta

import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from tenacity import retry, stop_after_attempt, wait_exponential

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ── data definitions ──────────────────────────────────────────────────────────

CATEGORIES = [
    "Groceries", "Dining", "Transport", "Subscriptions",
    "Shopping", "Health", "Utilities", "Entertainment", "Travel",
]

MERCHANTS = {
    "Groceries":     [("Aldi", "EUR", 35, 80), ("Lidl", "EUR", 25, 70), ("Rewe", "EUR", 40, 90)],
    "Dining":        [("Starbucks", "EUR", 4, 8), ("Local Bistro", "EUR", 15, 35), ("Burger King", "EUR", 8, 14)],
    "Transport":     [("Deutsche Bahn", "EUR", 20, 120), ("Uber", "EUR", 6, 25), ("Shell", "EUR", 40, 80)],
    "Subscriptions": [("Netflix", "EUR", 15, 15), ("Spotify", "EUR", 10, 10), ("YouTube Premium", "EUR", 12, 12)],
    "Shopping":      [("Amazon", "USD", 15, 120), ("Zara", "USD", 40, 150), ("H&M", "USD", 25, 80)],
    "Health":        [("Gym Membership", "EUR", 30, 30), ("Pharmacy", "EUR", 8, 40), ("Doctor Visit", "EUR", 25, 60)],
    "Utilities":     [("Electric Company", "EUR", 50, 90), ("Internet Provider", "EUR", 35, 35)],
    "Entertainment": [("Cinema", "EUR", 10, 20), ("Steam", "USD", 5, 60), ("Book Shop", "EUR", 10, 30)],
    "Travel":        [("Airbnb", "EUR", 60, 300), ("Booking.com", "EUR", 80, 400), ("Ryanair", "EUR", 30, 200)],
}

INCOME_MERCHANTS = [
    ("Employer", "EUR", 2800, 3200),
    ("Freelance Client", "USD", 300, 800),
    ("Interest", "EUR", 5, 20),
]

BUDGETS = {
    "Groceries":     250,
    "Dining":        120,
    "Transport":     100,
    "Subscriptions": 40,
    "Shopping":      150,
    "Health":        80,
    "Utilities":     130,
    "Entertainment": 60,
    "Travel":        200,
}

ACCOUNTS = ["HDFC Savings", "Chase Checking", "N26 Main"]

TRANSACTION_HEADERS = [
    "transaction_id", "date", "merchant", "amount", "currency",
    "type", "category", "account", "notes",
]
BUDGET_HEADERS = ["category", "monthly_budget_eur"]


# ── generation helpers ────────────────────────────────────────────────────────

def _rand_date_in_month(year: int, month: int) -> str:
    first = date(year, month, 1)
    if month == 12:
        last = date(year, 12, 31)
    else:
        last = date(year, month + 1, 1) - timedelta(days=1)
    delta = (last - first).days
    return (first + timedelta(days=random.randint(0, delta))).isoformat()


def _months_back(n: int) -> list[tuple[int, int]]:
    today = date.today()
    months = []
    y, m = today.year, today.month
    for _ in range(n):
        months.append((y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return list(reversed(months))


def generate_transactions(num_months: int = 6) -> list[list]:
    rows = []
    txn_counter = 1
    months = _months_back(num_months)

    for year, month in months:
        # Salary income — always first of month
        for merchant, currency, lo, hi in INCOME_MERCHANTS[:1]:  # salary only, monthly
            tid = f"txn_{year}{month:02d}_{txn_counter:04d}"
            rows.append([
                tid,
                date(year, month, 1).isoformat(),
                merchant,
                f"{random.uniform(lo, hi):.2f}",
                currency,
                "income",
                "Salary",
                "HDFC Savings",
                f"{date(year, month, 1).strftime('%B')} salary",
            ])
            txn_counter += 1

        # Freelance income — 0-1 times per month
        if random.random() > 0.4:
            merchant, currency, lo, hi = INCOME_MERCHANTS[1]
            tid = f"txn_{year}{month:02d}_{txn_counter:04d}"
            rows.append([
                tid,
                _rand_date_in_month(year, month),
                merchant,
                f"{random.uniform(lo, hi):.2f}",
                currency,
                "income",
                "Freelance",
                "Chase Checking",
                "",
            ])
            txn_counter += 1

        # Interest income — every month
        merchant, currency, lo, hi = INCOME_MERCHANTS[2]
        tid = f"txn_{year}{month:02d}_{txn_counter:04d}"
        rows.append([
            tid,
            date(year, month, 1).isoformat(),
            merchant,
            f"{random.uniform(lo, hi):.2f}",
            currency,
            "income",
            "Interest",
            "HDFC Savings",
            "",
        ])
        txn_counter += 1

        # Expenses by category
        for category, merchants in MERCHANTS.items():
            # Subscriptions appear every month; others have some randomness
            freq = 1.0 if category == "Subscriptions" else random.uniform(0.5, 1.0)
            num_txns = max(1, int(freq * random.randint(2, 5)))
            for _ in range(num_txns):
                merchant, currency, lo, hi = random.choice(merchants)
                # Subscriptions use fixed amounts
                amount = lo if category == "Subscriptions" else random.uniform(lo, hi)
                tid = f"txn_{year}{month:02d}_{txn_counter:04d}"
                rows.append([
                    tid,
                    _rand_date_in_month(year, month),
                    merchant,
                    f"{amount:.2f}",
                    currency,
                    "expense",
                    category,
                    random.choice(ACCOUNTS),
                    "",
                ])
                txn_counter += 1

    return rows


def generate_budgets() -> list[list]:
    return [[category, str(amount)] for category, amount in BUDGETS.items()]


# ── Sheets client ─────────────────────────────────────────────────────────────

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
    # Write scope needed to push data
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.file",
    ]
    creds = Credentials.from_service_account_info(key_data, scopes=scopes)
    return gspread.authorize(creds)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _write_tab(ws: gspread.Worksheet, headers: list[str], rows: list[list]) -> None:
    ws.clear()
    ws.append_row(headers, value_input_option="RAW")
    if rows:
        ws.append_rows(rows, value_input_option="RAW")
    logger.info("Wrote %d rows to tab '%s'", len(rows), ws.title)


# ── main ──────────────────────────────────────────────────────────────────────

def generate_and_push() -> None:
    sheet_id = os.getenv("GOOGLE_SHEET_ID", "")
    tx_tab = os.getenv("GOOGLE_TRANSACTIONS_TAB", "Transactions")
    budget_tab = os.getenv("GOOGLE_BUDGETS_TAB", "Budgets")
    if not sheet_id:
        raise EnvironmentError("GOOGLE_SHEET_ID must be set")

    logger.info("Generating 6 months of dummy data")
    transactions = generate_transactions(num_months=6)
    budgets = generate_budgets()
    logger.info("Generated %d transactions and %d budget rows", len(transactions), len(budgets))

    logger.info("Connecting to Google Sheets")
    gc = _get_gspread_client()
    sheet = gc.open_by_key(sheet_id)

    tx_ws = sheet.worksheet(tx_tab)
    budget_ws = sheet.worksheet(budget_tab)

    _write_tab(tx_ws, TRANSACTION_HEADERS, transactions)
    _write_tab(budget_ws, BUDGET_HEADERS, budgets)

    logger.info("Done — sheet populated with dummy data")


if __name__ == "__main__":
    generate_and_push()
