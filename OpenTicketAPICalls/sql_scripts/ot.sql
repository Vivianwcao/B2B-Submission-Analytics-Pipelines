-- Run once before ingesting data
-- 1. Create isolated schema
CREATE DATABASE IF NOT EXISTS submission_analytics;

-- 2. Create dedicated application user
CREATE USER 'vivian' @'%' IDENTIFIED BY '12345vivian';

GRANT ALL PRIVILEGES ON submission_analytics.* TO 'vivian' @'%';

FLUSH PRIVILEGES;

-- Do this to allow user vivian to Read-Only (SELECT) access (select, join , etc) on emi_v3
GRANT
SELECT
	ON emi_v3.* TO 'vivian' @'%';

FLUSH PRIVILEGES;

-- 3. Pre-create tables with precise data types and automatic timestamps
CREATE TABLE submission_analytics.opentickets (
	receipt_id VARCHAR(15) NOT NULL,
	ticket_number VARCHAR(20) NOT NULL,
	supplier VARCHAR(200),
	supplier_duns VARCHAR(20),
	buyer VARCHAR(200),
	buyer_duns VARCHAR(20),
	ticket_status VARCHAR(20),
	last_action_timestamp DATETIME NOT NULL,
	submitted_timestamp DATETIME,
	last_submitted_timestamp DATETIME,
	approved_timestamp DATETIME,
	cancelled_timestamp DATETIME,
	last_disputed_timestamp DATETIME,
	ticket_created_timestamp DATETIME,
	service_date_from DATETIME,
	service_date_to DATETIME,
	ticket_created_action VARCHAR(20),
	ticket_created_name VARCHAR(100),
	ticket_created_email VARCHAR(200),
	total_amount DECIMAL(12, 2),
	receipt_type VARCHAR(20),
	currency VARCHAR(10),
	invoiced_status VARCHAR(20),
	invoice_number VARCHAR(20),
	submission_source VARCHAR(15),
	afe VARCHAR(30),
	cost_center VARCHAR(30),
	major VARCHAR(20),
	minor VARCHAR(20),
	gl VARCHAR(40),
	href VARCHAR(200),
	ingested_at DATETIME,
	-- These columns populate themselves completely automatically
	created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
	PRIMARY KEY (receipt_id)
);

ALTER TABLE
	submission_analytics.opentickets ALGORITHM = inplace,
	LOCK = none,
MODIFY
	COLUMN ticket_number varchar(40),
MODIFY
	COLUMN ticket_status VARCHAR(30),
MODIFY
	COLUMN ticket_created_action VARCHAR(30),
MODIFY
	COLUMN receipt_type VARCHAR(30),
MODIFY
	COLUMN invoiced_status VARCHAR(40),
MODIFY
	COLUMN invoice_number VARCHAR(40),
MODIFY
	COLUMN submission_source VARCHAR(30);

ALTER TABLE
	submission_analytics.opentickets
MODIFY
	COLUMN invoice_number VARCHAR(250);
	

CREATE
OR REPLACE VIEW openticket_monthly_supplier_submission_source AS WITH stats AS (
	SELECT
		supplier,
		-- This turns "2024-08-22 04:57:13" into a real Date object: 2024-08-01
		date(
			ticket_created_timestamp - INTERVAL DAY(ticket_created_timestamp) - 1 DAY
		) AS MONTH,
		submission_source,
		count(receipt_id) AS ticket_count,
		sum(total_amount) AS ticket_amount,
		sum(ticket_status = 'CANCELLED') AS canceled,
		sum(last_disputed_timestamp IS NOT NULL) AS disputed,
		sum(
			ticket_status = 'APPROVED'
			AND last_disputed_timestamp IS NULL
		) AS approved_without_dispute,
		round(
			avg(
				CASE
					WHEN service_date_to < ticket_created_timestamp THEN timestampdiff(DAY, service_date_to, ticket_created_timestamp)
					ELSE NULL
				END
			),
			1
		) AS avg_submission_lag_days,
		round(
			avg(
				CASE
					WHEN approved_timestamp > service_date_to THEN timestampdiff(DAY, service_date_to, approved_timestamp)
					ELSE NULL
				END
			),
			1
		) AS avg_approved_days
	FROM
		submission_analytics.opentickets
	GROUP BY
		MONTH,
		supplier,
		submission_source
	ORDER BY
		supplier ASC,
		MONTH ASC,
		submission_source ASC
)
SELECT
	supplier,
	MONTH,
	submission_source,
	ticket_count,
	ticket_amount,
	avg_submission_lag_days,
	avg_approved_days,
	canceled,
	round(canceled * 100.0 / nullif(ticket_count, 0), 1) AS 'canceled%',
	disputed,
	round(disputed * 100.0 / nullif(ticket_count, 0), 1) AS 'disputed%',
	approved_without_dispute,
	round(
		approved_without_dispute * 100.0 / nullif(ticket_count, 0),
		1
	) AS 'approved_without_dispute%'
FROM
	stats;

CREATE
OR REPLACE VIEW openticket_quarterly_supplier_submission_source AS
SELECT
	supplier,
	MAKEDATE(YEAR(MONTH), 1) + INTERVAL (QUARTER(MONTH) - 1) * 3 MONTH AS quarter,
	submission_source,
	sum(ticket_count) AS ticket_count,
	sum(ticket_amount) AS ticket_amount,
	round(
		sum(avg_submission_lag_days * ticket_count) / nullif(sum(ticket_count), 0),
		1
	) AS avg_submission_lag_days,
	round(
		sum(avg_approved_days * ticket_count) / nullif(sum(ticket_count), 0),
		1
	) AS avg_approved_days,
	sum(canceled) AS canceled,
	round(
		sum(canceled) * 100.0 / nullif(sum(ticket_count), 0),
		1
	) AS 'canceled%',
	sum(disputed) AS disputed,
	round(
		sum(disputed) * 100.0 / nullif(sum(ticket_count), 0),
		1
	) AS 'disputed%',
	sum(approved_without_dispute) AS approved_without_dispute,
	round(
		sum(approved_without_dispute) * 100.0 / nullif(sum(ticket_count), 0),
		1
	) AS 'approved_without_dispute%'
	/* Based on the aggregated monthly view */
FROM
	openticket_monthly_supplier_submission_source
GROUP BY
	supplier,
	quarter,
	submission_source;

CREATE
OR REPLACE VIEW openticket_quarterly_supplier_direct_entry_data AS
SELECT
	supplier,
	-- remain a datetime object : 2024-07-01	
	MAKEDATE(YEAR(ticket_created_timestamp), 1) + INTERVAL (QUARTER(ticket_created_timestamp) - 1) * 3 MONTH AS quarter,
	ticket_created_name,
	count(ticket_created_name) AS cn,
	ticket_created_email,
	count(ticket_created_email) AS ce
FROM
	submission_analytics.opentickets
WHERE
	submission_source != 'EMI'
GROUP BY
	supplier,
	quarter,
	ticket_created_name,
	ticket_created_email
ORDER BY
	supplier ASC,
	quarter ASC,
	cn DESC;

CREATE
OR REPLACE VIEW openticket_semiannual_supplier_direct_entry_supplier_data AS
SELECT
	supplier,
	CASE
		WHEN MONTH(ticket_created_timestamp) <= 6 THEN makedate(year(ticket_created_timestamp), 1)
		ELSE date_add(
			makedate(year(ticket_created_timestamp), 1),
			INTERVAL 6 MONTH
		)
	END AS semiannual,
	buyer,
	count(receipt_id) AS ticket_count,
	sum(total_amount) AS ticket_amount
FROM
	submission_analytics.opentickets
WHERE
	submission_source != 'EMI'
GROUP BY
	supplier,
	semiannual,
	buyer
ORDER BY
	supplier ASC,
	semiannual ASC,
	ticket_count DESC EXPLAIN
SELECT
	sa.supplier,
	sa.buyer,
	count(di.`number`) AS EMI_flipped_count,
	count(sa.receipt_id) AS ticket_count
FROM
	submission_analytics.opentickets AS sa
	LEFT JOIN emi_v3.data_invoice di ON sa.supplier_duns = di.remit_to_duns COLLATE utf8mb4_0900_ai_ci
	AND sa.buyer_duns = di.bill_to_duns COLLATE utf8mb4_0900_ai_ci
	AND find_in_set(
		di.`number` COLLATE utf8mb4_0900_ai_ci,
		REPLACE(sa.invoice_number, ' ', '')
	) > 0
GROUP BY
	sa.supplier,
	sa.buyer
ORDER BY
	sa.supplier ASC,
	sa.buyer ASC -- create speedy index for mapping
	CREATE INDEX idx_tickets_dedup ON submission_analytics.opentickets (ticket_number, ticket_created_timestamp);


-- relate to emi_v3 tables
-- optimized
WITH invoiced AS (
	SELECT
		invoice_number,
		receipt_id
	FROM
		submission_analytics.invoice_numbers
	GROUP BY
		invoice_number,
		receipt_id
),
uq_data_invoice AS(
	SELECT
		`number` COLLATE utf8mb4_0900_ai_ci AS clean_number,
		remit_to_duns COLLATE utf8mb4_0900_ai_ci AS clean_supplier_duns,
		bill_to_duns COLLATE utf8mb4_0900_ai_ci AS clean_buyer_duns
	FROM
		emi_v3.data_invoice
	GROUP BY
		`number`,
		remit_to_duns,
		bill_to_duns
),
uq_data_ticket AS(
	SELECT
		`number` COLLATE utf8mb4_0900_ai_ci AS clean_number,
		vendor_duns COLLATE utf8mb4_0900_ai_ci AS clean_supplier_duns,
		ship_to_duns COLLATE utf8mb4_0900_ai_ci AS clean_buyer_duns,
		max(invoice_operation_id) AS flipped_id
	FROM
		emi_v3.data_ticket
	GROUP BY
		`number`,
		vendor_duns,
		ship_to_duns
)
SELECT
	ot.supplier,
	ot.buyer,
	count(DISTINCT ot.ticket_number) AS api_ticket_cnt,
	count(
		DISTINCT CASE
			WHEN ot.submission_source = 'EMI' THEN ot.ticket_number
		END
	) api_ticket_cnt_EMI,
	count(DISTINCT ut.clean_number) AS db_ticket_cnt_EMI,
	count(
		DISTINCT CASE
			WHEN ot.invoice_number IS NOT NULL THEN ot.ticket_number
		END
	) AS api_flipped_ticket_cnt,
	count(
		DISTINCT CASE
			WHEN ut.flipped_id IS NOT NULL THEN ut.clean_number
		END
	) AS db_flipped_ticket_cnt_EMI,
	count(DISTINCT invoiced.invoice_number) AS api_flipped_invoice_cnt,
	count(DISTINCT ui.clean_number) AS db_flipped_invoice_cnt_EMI
FROM
	submission_analytics.opentickets ot
	LEFT JOIN invoiced ON invoiced.receipt_id = ot.receipt_id
	LEFT JOIN uq_data_ticket ut ON ut.clean_number = ot.ticket_number
	AND ot.supplier_duns = ut.clean_supplier_duns
	AND ot.buyer_duns = ut.clean_buyer_duns
	LEFT JOIN uq_data_invoice ui ON ui.clean_number = invoiced.invoice_number
	AND ot.supplier_duns = ui.clean_supplier_duns
	AND ot.buyer_duns = ui.clean_buyer_duns
GROUP BY
	ot.supplier,
	ot.buyer;


-- find ticket numbers with multiple submissions (Low I/O, High CPU)
EXPLAIN WITH ranked_tickets AS (
	SELECT
		*,
		count(*) over (PARTITION by ticket_number) AS cnt,
		row_number() over (
			PARTITION by ticket_number
			ORDER BY
				ticket_created_timestamp ASC
		) AS created_order
	FROM
		submission_analytics.opentickets
)
SELECT
	*
FROM
	ranked_tickets
WHERE
	cnt > 1
ORDER BY
	ticket_number ASC,
	created_order ASC;

-- find ticket numbers with multiple submissions (High I/O, Low CPU)
EXPLAIN
SELECT
	t.*,
	d.cnt,
	row_number() over (
		PARTITION by ticket_number
		ORDER BY
			ticket_created_timestamp ASC
	) AS created_order
FROM
	submission_analytics.opentickets t
	INNER JOIN (
		SELECT
			ticket_number,
			count(*) AS cnt
		FROM
			submission_analytics.opentickets
		GROUP BY
			ticket_number
		HAVING
			count(*) > 1
	) d ON t.ticket_number = d.ticket_number
ORDER BY
	t.ticket_number ASC,
	created_order ASC;

-- find true duplicate ticket numbers (same created timestamp)
-- 0 - meaning updates by the same receipt id
EXPLAIN
SELECT
	t.*,
	d.cnt
FROM
	submission_analytics.opentickets t
	JOIN (
		SELECT
			ticket_number,
			ticket_created_timestamp,
			count(*) AS cnt
		FROM
			submission_analytics.opentickets
		GROUP BY
			ticket_number,
			ticket_created_timestamp
		HAVING
			count(*) > 1
	) d ON t.ticket_number = d.ticket_number
ORDER BY
	t.ticket_number ASC;

-- find out how many tickets with multiple receipt ids (re-submissions)
EXPLAIN
SELECT
	SUM(cnt - 1)
FROM
	(
		SELECT
			ticket_number,
			COUNT(*) AS cnt
		FROM
			submission_analytics.opentickets
		GROUP BY
			ticket_number
		HAVING
			COUNT(*) > 1
	) d;


-- Drop the old raw index
DROP INDEX idx_raw_ot_agg ON submission_analytics.opentickets;
-- Index for the raw opentickets table
CREATE INDEX idx_raw_ot_agg ON submission_analytics.opentickets (
	supplier,
	(
		DATE(
			ticket_created_timestamp - INTERVAL DAY(ticket_created_timestamp) - 1 DAY
		)
	),
	-- The calculation is indexed!
	submission_source,
	buyer
);