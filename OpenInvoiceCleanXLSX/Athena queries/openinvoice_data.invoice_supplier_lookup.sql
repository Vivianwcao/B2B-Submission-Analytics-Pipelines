CREATE
OR REPLACE VIEW openinvoice_data.invoice_supplier_lookup AS
SELECT
    supplierduns,
    MIN(supplier) AS supplier
FROM
    openinvoice_data.invoice_deduped
GROUP BY
    supplierduns