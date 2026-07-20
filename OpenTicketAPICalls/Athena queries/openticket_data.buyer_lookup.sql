CREATE
OR REPLACE VIEW openticket_data.buyer_lookup AS
SELECT
    buyer_duns,
    MIN(buyer) AS buyer
FROM
    openticket_data.tickets_deduped
GROUP BY
    buyer_duns