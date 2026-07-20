CREATE
OR REPLACE VIEW openinvoice_data.invoice_deduped AS
SELECT
    *
FROM
    (
        SELECT
            *,
            ROW_NUMBER() OVER (
                PARTITION BY invoiceno,
                STATUS
                ORDER BY
                    ingestedat DESC
            ) AS rn
        FROM
            openinvoice_data.invoices
    )
WHERE
    rn = 1;