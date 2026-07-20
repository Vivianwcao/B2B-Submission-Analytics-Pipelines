CREATE
OR REPLACE VIEW openticket_data.tickets_buyer_monthly_join_names AS
SELECT
    t.*,
    b.buyer
FROM
    openticket_data.tickets_buyer_monthly t
    LEFT JOIN openticket_data.buyer_lookup b ON t.buyer_duns = b.buyer_duns