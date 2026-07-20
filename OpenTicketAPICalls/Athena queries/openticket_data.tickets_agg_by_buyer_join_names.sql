CREATE
OR REPLACE VIEW openticket_data.tickets_agg_by_buyer_join_names AS
SELECT
    t.*,
    b.buyer
FROM
    openticket_data.tickets_agg_by_buyer t
    LEFT JOIN openticket_data.buyer_lookup b ON t.buyer_duns = b.buyer_duns