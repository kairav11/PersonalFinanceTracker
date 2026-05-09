WITH

transactions AS (
    SELECT * FROM {{ ref('stg_transactions') }}
),

monthly AS (
    SELECT
        DATE_FORMAT(date, 'yyyy-MM')                                        AS year_month,
        CAST(SUM(CASE WHEN type = 'income'  THEN amount_eur ELSE 0 END) AS DECIMAL(18, 2)) AS total_income_eur,
        CAST(SUM(CASE WHEN type = 'expense' THEN amount_eur ELSE 0 END) AS DECIMAL(18, 2)) AS total_expense_eur
    FROM transactions
    GROUP BY DATE_FORMAT(date, 'yyyy-MM')
),

with_net AS (
    SELECT
        year_month,
        total_income_eur,
        total_expense_eur,
        CAST(total_income_eur - total_expense_eur AS DECIMAL(18, 2)) AS net_eur
    FROM monthly
),

with_rolling AS (
    SELECT
        year_month,
        total_income_eur,
        total_expense_eur,
        net_eur,
        CAST(
            AVG(net_eur) OVER (
                ORDER BY year_month
                ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
            ) AS DECIMAL(18, 2)
        ) AS rolling_3m_avg_net_eur
    FROM with_net
)

SELECT * FROM with_rolling
ORDER BY year_month
