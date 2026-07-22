CREATE TABLE IF NOT EXISTS agent_releases (
    id BIGSERIAL PRIMARY KEY,
    version VARCHAR(64) NOT NULL UNIQUE,
    manifest JSONB NOT NULL,
    active BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS agent_deployments (
    id BIGSERIAL PRIMARY KEY,
    release_id BIGINT NOT NULL REFERENCES agent_releases(id),
    store_code VARCHAR(64) NOT NULL REFERENCES stores(store_code),
    status VARCHAR(32) NOT NULL,
    message TEXT,
    current_version VARCHAR(64),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (release_id, store_code)
);

CREATE INDEX IF NOT EXISTS idx_agent_releases_active
    ON agent_releases (active, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_agent_deployments_store
    ON agent_deployments (store_code, updated_at DESC);
