CREATE TABLE IF NOT EXISTS post_eod_file_checks (
    id BIGSERIAL PRIMARY KEY,
    store_code VARCHAR(64) NOT NULL REFERENCES stores(store_code),
    eod_date DATE NOT NULL,
    eod_completed_at TIMESTAMP NOT NULL,
    checked_at TIMESTAMP NOT NULL,
    result JSONB NOT NULL,
    passed BOOLEAN NOT NULL,
    details TEXT NOT NULL DEFAULT '',
    alert_id BIGINT UNIQUE,
    email_due_at TIMESTAMP,
    UNIQUE (store_code, eod_date)
);

CREATE INDEX IF NOT EXISTS idx_post_eod_file_checks_email_due
    ON post_eod_file_checks (email_due_at, alert_id)
    WHERE passed = FALSE;
