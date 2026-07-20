CREATE
OR REPLACE VIEW openinvoice_data.invoice_supplier_monthly AS WITH normalized AS (
    SELECT
        *,
        CASE
            WHEN submissiontype IN ('B2B', 'EMI', 'API') THEN 'EMI'
            ELSE 'Direct Entry'
        END AS submission_source_group
    FROM
        openinvoice_data.invoice_deduped
    WHERE
        STATUS NOT IN ('Cancelled', 'Disputed') --   keep nulls (no status for some buyers like Green engergies)
        OR STATUS IS NULL
)
SELECT
    supplier,
    submission_source_group,
    date_trunc('month', statusdate) AS invoice_month,
    COUNT(*) AS invoice_count,
    SUM(amount) AS total_amount,
    AVG(
        CASE
            WHEN STATUS = 'Approved'
            OR STATUS IS NULL THEN date_diff('day', invoicedate, statusdate)
        END
    ) AS avg_approval_days,
    AVG(
        CASE
            WHEN STATUS IN ('Submitted', 'Saved', 'Re-Submitted')
            OR STATUS IS NULL THEN date_diff('day', invoicedate, statusdate)
        END
    ) AS avg_submission_lag_days
FROM
    normalized
GROUP BY
    supplier,
    submission_source_group,
    date_trunc('month', statusdate);