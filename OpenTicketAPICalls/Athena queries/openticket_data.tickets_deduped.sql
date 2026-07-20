CREATE
OR REPLACE VIEW openticket_data.tickets_deduped AS
SELECT
    *
FROM
    (
        SELECT
            *,
            ROW_NUMBER() OVER (
                PARTITION BY ticket_number
                ORDER BY
                    ingested_at DESC
            ) AS rn
        FROM
            openticket_data.tickets
    )
WHERE
    rn = 1;