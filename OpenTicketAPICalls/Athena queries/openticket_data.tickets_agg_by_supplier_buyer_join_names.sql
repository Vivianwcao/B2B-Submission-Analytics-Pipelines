CREATE
OR REPLACE VIEW openticket_data.tickets_agg_by_supplier_buyer_join_names AS
SELECT
    t.*,
    s.supplier,
    b.buyer
FROM
    openticket_data.tickets_agg_by_supplier_buyer t
    LEFT JOIN openticket_data.supplier_lookup s ON t.supplier_duns = s.supplier_duns
    LEFT JOIN openticket_data.buyer_lookup b ON t.buyer_duns = b.buyer_duns