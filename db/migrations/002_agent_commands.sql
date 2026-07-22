CREATE TABLE IF NOT EXISTS agent_commands (
    id BIGSERIAL PRIMARY KEY,
    store_code VARCHAR(64) NOT NULL REFERENCES stores(store_code),
    service_name VARCHAR(128) NOT NULL,
    action VARCHAR(16) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'PENDING',
    message TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    CONSTRAINT chk_agent_commands_action CHECK (action IN ('start', 'stop', 'restart')),
    CONSTRAINT chk_agent_commands_status CHECK (status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED'))
);

CREATE INDEX IF NOT EXISTS idx_agent_commands_next
    ON agent_commands (store_code, status, created_at, id);
