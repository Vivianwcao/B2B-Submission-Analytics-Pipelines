CREATE
OR REPLACE VIEW openinvoice_data.invoice_supplier_monthly_join_names AS
SELECT
    n.*,
    l.supplier
FROM
    openinvoice_data.invoice_supplier_monthly AS n
    LEFT JOIN openinvoice_data.invoice_supplier_lookup AS l ON n.supplierduns = l.supplierduns;