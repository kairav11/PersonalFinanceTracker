WITH

source AS (
    SELECT * FROM {{ source('bronze', 'budgets') }}
),

cast_and_clean AS (
    SELECT
        TRIM(category)                                 AS category,
        CAST(monthly_budget_eur AS DECIMAL(18, 2))     AS monthly_budget_eur
    FROM source
    WHERE category IS NOT NULL
      AND TRIM(category) != ''
      AND monthly_budget_eur IS NOT NULL
)

SELECT * FROM cast_and_clean
