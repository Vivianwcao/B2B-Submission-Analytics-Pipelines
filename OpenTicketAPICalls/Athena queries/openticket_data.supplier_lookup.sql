CREATE
OR REPLACE VIEW openticket_data.supplier_lookup AS
SELECT
    supplier_duns,
    MIN(supplier) AS supplier
FROM
    openticket_data.tickets_deduped
GROUP BY
    supplier_duns