WITH

transactions AS (
    SELECT * FROM {{ ref('stg_transactions') }}
    WHERE type = 'expense'
),

merchant_medians AS (
    SELECT
        merchant,
        PERCENTILE(amount_eur, 0.5) AS median_amount_eur
    FROM transactions
    GROUP BY merchant
),

within_tolerance AS (
    SELECT
        t.merchant,
        DATE_FORMAT(t.date, 'yyyy-MM') AS year_month,
        t.date,
        t.amount_eur
    FROM transactions t
    INNER JOIN merchant_medians m ON t.merchant = m.merchant
    WHERE t.amount_eur BETWEEN m.median_amount_eur * 0.98
                           AND m.median_amount_eur * 1.02
),

qualified AS (
    SELECT
        merchant,
        COUNT(DISTINCT year_month) AS occurrence_count,
        MIN(date)                  AS first_seen,
        MAX(date)                  AS last_seen
    FROM within_tolerance
    GROUP BY merchant
    HAVING COUNT(DISTINCT year_month) >= 3
),

final AS (
    SELECT
        q.merchant,
        CAST(m.median_amount_eur AS DECIMAL(18, 2)) AS estimated_monthly_cost_eur,
        q.first_seen,
        q.last_seen,
        CAST(q.occurrence_count AS INT)             AS occurrence_count
    FROM qualified q
    INNER JOIN merchant_medians m ON q.merchant = m.merchant
)

SELECT * FROM final
ORDER BY estimated_monthly_cost_eur DESC
