CREATE TABLE submission_analytics.invoice_numbers(
    id INT AUTO_INCREMENT,
    receipt_id VARCHAR(15) NOT NULL,
    invoice_number varchar(40),
    PRIMARY KEY(id),
    INDEX idx_receipt_id(receipt_id),
    CONSTRAINT fk_ticket_invoice_number FOREIGN KEY(receipt_id) REFERENCES submission_analytics.opentickets(receipt_id)
);

-- delete dup rows
DELETE t2
FROM
    submission_analytics.invoice_numbers t1
    JOIN submission_analytics.invoice_numbers t2 ON t1.receipt_id = t2.receipt_id
    AND t1.invoice_number = t2.invoice_number
    AND t2.id > t1.id;

-- count dups
WITH a AS (
    SELECT
        receipt_id,
        invoice_number,
        count(*) AS dup_count
    FROM
        submission_analytics.invoice_numbers
    GROUP BY
        receipt_id,
        invoice_number
    HAVING
        count(*) > 1
)
SELECT
    sum(dup_count -1)
FROM
    a -- count unique row
    WITH a AS (
        SELECT
            receipt_id,
            invoice_number,
            count(*) AS dup_count
        FROM
            submission_analytics.invoice_numbers
        GROUP BY
            receipt_id,
            invoice_number
        HAVING
            count(*) = 1
    )
SELECT
    sum(dup_count)
FROM
    a

ALTER TABLE
    submission_analytics.invoice_numbers
ADD
    CONSTRAINT uq_receipt_invoice UNIQUE(receipt_id, invoice_number);

ALTER TABLE
    submission_analytics.invoice_numbers
ADD
    created_at timestamp DEFAULT CURRENT_TIMESTAMP;