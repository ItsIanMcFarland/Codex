-- Sample SQL schema for reference.
CREATE TABLE IF NOT EXISTS hotels (
    id SERIAL PRIMARY KEY,
    domain VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255),
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS crawl_jobs (
    id SERIAL PRIMARY KEY,
    job_id UUID NOT NULL UNIQUE,
    hotel_id INTEGER NOT NULL REFERENCES hotels(id) ON DELETE CASCADE,
    status VARCHAR(32) NOT NULL DEFAULT 'queued',
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    metadata JSONB,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW() NOT NULL,
    completed_at TIMESTAMP WITHOUT TIME ZONE
);
CREATE INDEX IF NOT EXISTS idx_crawl_jobs_status ON crawl_jobs(status);

CREATE TABLE IF NOT EXISTS fetch_attempts (
    id SERIAL PRIMARY KEY,
    job_id INTEGER NOT NULL REFERENCES crawl_jobs(id) ON DELETE CASCADE,
    proxy VARCHAR(255),
    status_code INTEGER,
    success BOOLEAN NOT NULL DEFAULT FALSE,
    error TEXT,
    response_time_ms INTEGER,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW() NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fetch_attempts_job ON fetch_attempts(job_id);

CREATE TABLE IF NOT EXISTS discovered_links (
    id SERIAL PRIMARY KEY,
    job_id INTEGER NOT NULL REFERENCES crawl_jobs(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    network VARCHAR(32),
    source_url TEXT,
    last_seen TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW() NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT uq_discovered_links_job_url UNIQUE (job_id, url)
);
CREATE INDEX IF NOT EXISTS idx_discovered_links_url ON discovered_links(url);
