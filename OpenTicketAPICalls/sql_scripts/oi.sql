CREATE TABLE submission_analytics.openinvoice(
    invoice_number varchar(40) NOT NULL,
    supplier varchar(200) NOT NULL,
    supplier_duns varchar(20),
    buyer varchar(200) NOT NULL,
    buyer_duns varchar(20),
    invoice_date datetime,
    STATUS varchar(30),
    status_date datetime,
    current_owner varchar(100),
    amount decimal(12, 2),
    invoice_type varchar(100),
    submission_type varchar(50),
    ingested_at datetime,
    created_at timestamp DEFAULT CURRENT_TIMESTAMP,
    last_updated timestamp DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (invoice_number, supplier, buyer)
);

-- update submission_analytics.openinvoice
-- set submission_type = case
-- 	when submission_type is null then null
-- 	when submission_type in ('B2B', 'EMI') then 'EMI'
-- 	else 'Direct Entry'
-- end;
-- Drop the old raw index
DROP INDEX idx_raw_oi_agg ON submission_analytics.openinvoice;

-- Index for the raw openinvoice table
CREATE INDEX idx_raw_oi_agg ON submission_analytics.openinvoice (
    supplier,
    (
        DATE(
            invoice_date - INTERVAL DAY(invoice_date) - 1 DAY
        )
    ),
    -- The calculation is indexed!
    submission_type,
    buyer
);


CREATE
OR REPLACE VIEW submission_analytics.openinvoice_monthly_supplier_submission_source AS EXPLAIN
SELECT
    oi.supplier,
    date(
        oi.invoice_date - INTERVAL DAY(oi.invoice_date) - 1 DAY
    ) AS MONTH,
    oi.submission_type,
    count(*) AS invoice_count,
    sum(oi.amount) AS invoice_amount
FROM
    submission_analytics.openinvoice oi
GROUP BY
    oi.supplier,
    MONTH,
    oi.submission_type
ORDER BY
    oi.supplier ASC,
    MONTH ASC,
    oi.submission_type ASC;

    *
FROM
    submission_analytics.join_oi_ot_monthly_supplier_buyers_submission_source_wide
ORDER BY
    supplier,
    MONTH,
    buyer;