WITH

source AS (
    SELECT * FROM {{ source('bronze', 'transactions') }}
),

deduped AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY transaction_id
            ORDER BY _ingested_at DESC
        ) AS _row_num
    FROM source
    WHERE transaction_id IS NOT NULL
      AND TRIM(transaction_id) != ''
),

latest AS (
    SELECT * FROM deduped WHERE _row_num = 1
),

cast_and_clean AS (
    SELECT
        TRIM(transaction_id)                              AS transaction_id,
        CAST(date AS DATE)                                AS date,
        TRIM(merchant)                                    AS merchant,
        CAST(amount AS DECIMAL(18, 2))                    AS amount,
        UPPER(TRIM(currency))                             AS currency,
        LOWER(TRIM(type))                                 AS type,
        NULLIF(TRIM(category), '')                        AS category,
        NULLIF(TRIM(account), '')                         AS account,
        NULLIF(TRIM(notes), '')                           AS notes,
        _source,
        _ingested_at
    FROM latest
),

with_fx AS (
    SELECT
        t.transaction_id,
        t.date,
        t.merchant,
        t.amount,
        t.currency,
        CAST(t.amount * f.rate_to_eur AS DECIMAL(18, 4)) AS amount_eur,
        t.type,
        t.category,
        t.account,
        t.notes,
        t._source,
        t._ingested_at
    FROM cast_and_clean t
    LEFT JOIN {{ ref('fx_rates') }} f
        ON t.currency = f.currency
)

SELECT * FROM with_fx
