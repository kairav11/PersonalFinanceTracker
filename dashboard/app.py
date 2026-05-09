import pandas as pd
import plotly.express as px
import streamlit as st
from databricks import sql as dbsql
from datetime import date

st.set_page_config(page_title="Wealth-Flow", layout="wide")
st.title("Wealth-Flow Lakehouse")
st.caption("Personal finance analytics — Databricks + dbt + Streamlit")

# ── connection ────────────────────────────────────────────────────────────────

def _get_connection():
    return dbsql.connect(
        server_hostname=st.secrets["DATABRICKS_HOST"],
        http_path=st.secrets["DATABRICKS_HTTP_PATH"],
        access_token=st.secrets["DATABRICKS_TOKEN"],
    )


def _run_query(sql: str) -> pd.DataFrame:
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchall_arrow().to_pandas()
    finally:
        conn.close()


# ── cached data loaders ───────────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def load_monthly_burn() -> pd.DataFrame:
    return _run_query(
        "SELECT * FROM workspace.gold.fct_monthly_burn ORDER BY year_month"
    )


@st.cache_data(ttl=3600)
def load_income_vs_expense() -> pd.DataFrame:
    return _run_query(
        "SELECT * FROM workspace.gold.fct_income_vs_expense ORDER BY year_month"
    )


@st.cache_data(ttl=3600)
def load_budget_variance() -> pd.DataFrame:
    return _run_query(
        "SELECT * FROM workspace.gold.fct_budget_variance ORDER BY year_month, category"
    )


@st.cache_data(ttl=3600)
def load_subscriptions() -> pd.DataFrame:
    return _run_query(
        "SELECT * FROM workspace.gold.dim_subscription_tracker"
        " ORDER BY estimated_monthly_cost_eur DESC"
    )


# ── panel helpers ─────────────────────────────────────────────────────────────

def _empty(label: str) -> None:
    st.info(f"No data available yet — {label}")


# ── panel 5: YTD summary (top of page) ───────────────────────────────────────

st.subheader("YTD Summary")
try:
    ive = load_income_vs_expense()
    if ive.empty:
        _empty("income vs expense")
    else:
        current_year = str(date.today().year)
        ytd = ive[ive["year_month"].str.startswith(current_year)]
        ytd_income  = float(ytd["total_income_eur"].sum())
        ytd_expense = float(ytd["total_expense_eur"].sum())
        ytd_net     = ytd_income - ytd_expense

        c1, c2, c3 = st.columns(3)
        c1.metric("YTD Total Earned (EUR)",  f"€{ytd_income:,.2f}")
        c2.metric("YTD Total Spent (EUR)",   f"€{ytd_expense:,.2f}")
        c3.metric("YTD Net Savings (EUR)",   f"€{ytd_net:,.2f}",
                  delta=f"€{ytd_net:,.2f}", delta_color="normal")
except Exception as exc:
    st.error(f"Could not load YTD summary: {exc}")

st.divider()

# ── panel 1: monthly burn by category ────────────────────────────────────────

st.subheader("Monthly Burn by Category")
try:
    burn = load_monthly_burn()
    expenses = burn[burn["type"] == "expense"]
    if expenses.empty:
        _empty("monthly burn")
    else:
        fig = px.bar(
            expenses,
            x="year_month",
            y="total_eur",
            color="category",
            barmode="stack",
            labels={"year_month": "Month", "total_eur": "Total (EUR)", "category": "Category"},
        )
        fig.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)
except Exception as exc:
    st.error(f"Could not load monthly burn: {exc}")

st.divider()

# ── panel 3: income vs expense ────────────────────────────────────────────────

st.subheader("Income vs. Expense")
try:
    ive = load_income_vs_expense()
    if ive.empty:
        _empty("income vs expense")
    else:
        melted = ive.melt(
            id_vars="year_month",
            value_vars=["total_income_eur", "total_expense_eur", "net_eur"],
            var_name="metric",
            value_name="eur",
        )
        label_map = {
            "total_income_eur":  "Income",
            "total_expense_eur": "Expense",
            "net_eur":           "Net",
        }
        melted["metric"] = melted["metric"].map(label_map)
        fig = px.line(
            melted,
            x="year_month",
            y="eur",
            color="metric",
            markers=True,
            labels={"year_month": "Month", "eur": "Amount (EUR)", "metric": ""},
        )
        fig.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)
except Exception as exc:
    st.error(f"Could not load income vs expense: {exc}")

st.divider()

# ── panel 2: budget variance ──────────────────────────────────────────────────

st.subheader("Budget Variance")
try:
    bv = load_budget_variance()
    if bv.empty:
        _empty("budget variance")
    else:
        available_months = sorted(bv["year_month"].unique(), reverse=True)
        current_month = date.today().strftime("%Y-%m")
        default = current_month if current_month in available_months else available_months[0]
        selected = st.selectbox("Select month", available_months, index=available_months.index(default))

        month_df = bv[bv["year_month"] == selected].copy()
        month_df["color"] = month_df["over_budget"].apply(
            lambda x: "Over budget" if x is True else "Within budget"
        )
        melted = month_df.melt(
            id_vars=["category", "color"],
            value_vars=["actual_eur", "budget_eur"],
            var_name="metric",
            value_name="eur",
        )
        melted["metric"] = melted["metric"].map({"actual_eur": "Actual", "budget_eur": "Budget"})

        fig = px.bar(
            melted,
            x="category",
            y="eur",
            color="metric",
            barmode="group",
            labels={"category": "Category", "eur": "Amount (EUR)", "metric": ""},
            color_discrete_map={"Actual": "#EF553B", "Budget": "#636EFA"},
        )
        # Highlight over-budget categories with a red marker
        over = month_df[month_df["over_budget"] == True]["category"].tolist()
        if over:
            st.caption(f"Over budget: {', '.join(over)}")
        st.plotly_chart(fig, use_container_width=True)
except Exception as exc:
    st.error(f"Could not load budget variance: {exc}")

st.divider()

# ── panel 4: subscription tracker ────────────────────────────────────────────

st.subheader("Recurring Subscriptions")
try:
    subs = load_subscriptions()
    if subs.empty:
        _empty("subscriptions")
    else:
        display = subs[[
            "merchant", "estimated_monthly_cost_eur",
            "occurrence_count", "first_seen", "last_seen",
        ]].rename(columns={
            "merchant":                  "Merchant",
            "estimated_monthly_cost_eur": "Monthly Cost (EUR)",
            "occurrence_count":          "Months Seen",
            "first_seen":                "First Seen",
            "last_seen":                 "Last Seen",
        })
        st.dataframe(display, use_container_width=True, hide_index=True)
except Exception as exc:
    st.error(f"Could not load subscriptions: {exc}")
