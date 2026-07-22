CREATE TABLE IF NOT EXISTS log_collection_requests (
    id BIGSERIAL PRIMARY KEY,
    store_code VARCHAR(64) NOT NULL REFERENCES stores(store_code),
    log_keys JSONB NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'PENDING',
    message TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    CONSTRAINT chk_log_collection_status
        CHECK (status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED'))
);

CREATE INDEX IF NOT EXISTS idx_log_collection_next
    ON log_collection_requests (store_code, status, created_at, id);
