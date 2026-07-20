CREATE
OR REPLACE VIEW openticket_data.tickets_supplier_monthly AS WITH normalized AS (
    SELECT
        *,
        CASE
            WHEN submissionSource IN ('EMI', 'API') THEN 'EMI'
            ELSE 'Direct Entry'
        END AS submission_source_group
    FROM
        openticket_data.tickets_deduped
)
SELECT
    supplier_duns,
    submission_source_group,
    date_trunc('month', submittedDatetime) AS activity_month,
    COUNT(*) AS ticket_count,
    SUM(totalAmount) AS total_amount,
    AVG(
        date_diff('day', lastSubmittedDatetime, approvedDatetime)
    ) AS avg_approval_days,
    AVG(
        date_diff('day', serviceDateTo, submittedDatetime)
    ) AS avg_submission_lag_days
FROM
    normalized
GROUP BY
    supplier_duns,
    submission_source_group,
    date_trunc('month', submittedDatetime);