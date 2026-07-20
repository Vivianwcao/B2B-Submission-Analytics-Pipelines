CREATE TABLE submission_analytics.parties(
    duns VARCHAR(20) NOT NULL,
    name VARCHAR(200),
    party_type ENUM('supplier', 'buyer'),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (duns)
);