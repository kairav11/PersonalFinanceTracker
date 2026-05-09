WITH

transactions AS (
    SELECT * FROM {{ ref('stg_transactions') }}
    WHERE category IS NOT NULL
),

monthly_agg AS (
    SELECT
        DATE_FORMAT(date, 'yyyy-MM')            AS year_month,
        category,
        type,
        CAST(SUM(amount_eur) AS DECIMAL(18, 2)) AS total_eur
    FROM transactions
    GROUP BY DATE_FORMAT(date, 'yyyy-MM'), category, type
),

with_ytd AS (
    SELECT
        year_month,
        category,
        type,
        total_eur,
        CAST(
            SUM(total_eur) OVER (
                PARTITION BY LEFT(year_month, 4), category, type
                ORDER BY year_month
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS DECIMAL(18, 2)
        ) AS ytd_total_eur
    FROM monthly_agg
)

SELECT * FROM with_ytd
ORDER BY year_month, category, type
