CREATE
OR REPLACE VIEW openticket_data.tickets_supplier_monthly_join_names AS
SELECT
    t.*,
    s.supplier
FROM
    openticket_data.tickets_supplier_monthly t
    LEFT JOIN openticket_data.supplier_lookup s ON t.supplier_duns = s.supplier_duns