CREATE
OR REPLACE VIEW submission_analytics.join_oi_ot_monthly_supplier_submission_source AS WITH all_keys AS (
    SELECT
        supplier,
        MONTH,
        submission_type
    FROM
        submission_analytics.openinvoice_monthly_supplier_submission_source
    UNION
    SELECT
        supplier,
        MONTH,
        submission_source AS submission_type
    FROM
        submission_analytics.openticket_monthly_supplier_submission_source
)
SELECT
    k.supplier,
    k.month,
    k.submission_type,
    oi.invoice_count,
    oi.invoice_amount,
    ot.ticket_count,
    ot.ticket_amount
FROM
    all_keys k
    LEFT JOIN submission_analytics.openinvoice_monthly_supplier_submission_source oi ON oi.supplier = k.supplier
    AND oi.month = k.month
    AND oi.submission_type = k.submission_type
    LEFT JOIN submission_analytics.openticket_monthly_supplier_submission_source ot ON ot.supplier = k.supplier
    AND ot.month = k.month
    AND ot.submission_source = k.submission_type;

SELECT
    *
FROM
    submission_analytics.join_oi_ot_monthly_supplier_submission_source
ORDER BY
    supplier,
    MONTH,
    submission_type;

CREATE
OR REPLACE VIEW submission_analytics.join_oi_ot_monthly_supplier_submission_source_wide AS
SELECT
    supplier,
    MONTH,
    --     TICKET: EMI
    SUM(
        CASE
            WHEN submission_type = 'EMI' THEN ticket_count
        END
    ) AS ticket_count_EMI,
    SUM(
        CASE
            WHEN submission_type = 'EMI' THEN ticket_amount
        END
    ) AS ticket_amount_EMI,
    --     TICKET: Direct Entry
    SUM(
        CASE
            WHEN submission_type = 'Direct Entry' THEN ticket_count
        END
    ) AS ticket_count_Direct_Entry,
    SUM(
        CASE
            WHEN submission_type = 'Direct Entry' THEN ticket_amount
        END
    ) AS ticket_amount_Direct_Entry,
    -- INVOICE: EMI
    SUM(
        CASE
            WHEN submission_type = 'EMI' THEN invoice_count
        END
    ) AS invoice_count_EMI,
    SUM(
        CASE
            WHEN submission_type = 'EMI' THEN invoice_amount
        END
    ) AS invoice_amount_EMI,
    --     INVOICE: Direct Entry
    SUM(
        CASE
            WHEN submission_type = 'Direct Entry' THEN invoice_count
        END
    ) AS invoice_count_Direct_Entry,
    SUM(
        CASE
            WHEN submission_type = 'Direct Entry' THEN invoice_amount
        END
    ) AS invoice_amount_Direct_Entry
FROM
    submission_analytics.join_oi_ot_monthly_supplier_submission_source
GROUP BY
    supplier,
    MONTH;

EXPLAIN
SELECT
    *
FROM
    submission_analytics.join_oi_ot_monthly_supplier_submission_source_wide
ORDER BY
    supplier,
    MONTH;

CREATE
OR REPLACE VIEW submission_analytics.join_oi_ot_monthly_supplier_buyers_submission_source AS WITH oi_agg AS (
    SELECT
        supplier,
        date(
            invoice_date - INTERVAL DAY(invoice_date) - 1 DAY
        ) AS MONTH,
        submission_type,
        buyer,
        count(*) AS oi_buyer_count,
        sum(amount) AS oi_amount
    FROM
        submission_analytics.openinvoice
    GROUP BY
        supplier,
        MONTH,
        submission_type,
        buyer
),
ot_agg AS (
    SELECT
        supplier,
        date(
            ticket_created_timestamp - INTERVAL DAY(ticket_created_timestamp) - 1 DAY
        ) AS MONTH,
        submission_source AS submission_type,
        buyer,
        count(*) AS ot_buyer_count,
        sum(total_amount) AS ot_amount
    FROM
        submission_analytics.opentickets
    GROUP BY
        supplier,
        MONTH,
        submission_source,
        buyer
),
all_keys AS (
    SELECT
        supplier,
        MONTH,
        submission_type,
        buyer
    FROM
        oi_agg
    UNION
    SELECT
        supplier,
        MONTH,
        submission_type,
        buyer
    FROM
        ot_agg
)
SELECT
    k.supplier,
    k.month,
    k.submission_type,
    k.buyer,
    oi_agg.oi_buyer_count,
    oi_agg.oi_amount,
    ot_agg.ot_buyer_count,
    ot_agg.ot_amount
FROM
    all_keys AS k
    LEFT JOIN oi_agg ON oi_agg.supplier = k.supplier
    AND oi_agg.month = k.month
    AND oi_agg.submission_type = k.submission_type
    AND oi_agg.buyer = k.buyer
    LEFT JOIN ot_agg ON ot_agg.supplier = k.supplier
    AND ot_agg.month = k.month
    AND ot_agg.submission_type = k.submission_type
    AND ot_agg.buyer = k.buyer;

CREATE
OR REPLACE VIEW submission_analytics.join_oi_ot_monthly_supplier_buyers_submission_source_wide AS
SELECT
    supplier,
    MONTH,
    buyer,
    --     TICKET: EMI
    SUM(
        CASE
            WHEN submission_type = 'EMI' THEN ot_buyer_count
        END
    ) AS ticket_count_EMI,
    SUM(
        CASE
            WHEN submission_type = 'EMI' THEN ot_amount
        END
    ) AS ticket_amount_EMI,
    --     TICKET: Direct Entry
    SUM(
        CASE
            WHEN submission_type = 'Direct Entry' THEN ot_buyer_count
        END
    ) AS ticket_count_Direct_Entry,
    SUM(
        CASE
            WHEN submission_type = 'Direct Entry' THEN ot_amount
        END
    ) AS ticket_amount_Direct_Entry,
    -- INVOICE: EMI
    SUM(
        CASE
            WHEN submission_type = 'EMI' THEN oi_buyer_count
        END
    ) AS invoice_count_EMI,
    SUM(
        CASE
            WHEN submission_type = 'EMI' THEN oi_amount
        END
    ) AS invoice_amount_EMI,
    --     INVOICE: Direct Entry
    SUM(
        CASE
            WHEN submission_type = 'Direct Entry' THEN oi_buyer_count
        END
    ) AS invoice_count_Direct_Entry,
    SUM(
        CASE
            WHEN submission_type = 'Direct Entry' THEN oi_amount
        END
    ) AS invoice_amount_Direct_Entry
FROM
    submission_analytics.join_oi_ot_monthly_supplier_buyers_submission_source
GROUP BY
    supplier,
    MONTH,
    buyer;

SELECT