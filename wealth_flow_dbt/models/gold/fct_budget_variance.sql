WITH

monthly_burn AS (
    SELECT * FROM {{ ref('fct_monthly_burn') }}
    WHERE type = 'expense'
),

budgets AS (
    SELECT * FROM {{ ref('stg_budgets') }}
),

actual AS (
    SELECT
        year_month,
        category,
        CAST(SUM(total_eur) AS DECIMAL(18, 2)) AS actual_eur
    FROM monthly_burn
    GROUP BY year_month, category
),

joined AS (
    SELECT
        a.year_month,
        a.category,
        a.actual_eur,
        b.monthly_budget_eur                                                         AS budget_eur,
        CAST(a.actual_eur - b.monthly_budget_eur AS DECIMAL(18, 2))                  AS variance_eur,
        CAST(
            CASE
                WHEN b.monthly_budget_eur IS NULL THEN NULL
                ELSE ROUND(
                    (a.actual_eur - b.monthly_budget_eur) / b.monthly_budget_eur * 100,
                    2
                )
            END AS DECIMAL(8, 2)
        )                                                                             AS variance_pct,
        CASE
            WHEN b.monthly_budget_eur IS NULL THEN NULL
            ELSE a.actual_eur > b.monthly_budget_eur
        END                                                                           AS over_budget
    FROM actual a
    LEFT JOIN budgets b ON a.category = b.category
)

SELECT * FROM joined
ORDER BY year_month, category
