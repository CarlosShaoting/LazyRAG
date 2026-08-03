-- +migrate Dialect postgres
ALTER TABLE plugin_sessions ADD COLUMN IF NOT EXISTS origin_host VARCHAR(32) NOT NULL DEFAULT 'lazymind';
ALTER TABLE plugin_sessions ADD COLUMN IF NOT EXISTS origin_ref VARCHAR(255) NOT NULL DEFAULT '';
ALTER TABLE plugin_sessions ADD COLUMN IF NOT EXISTS controller_host VARCHAR(32) NOT NULL DEFAULT 'lazymind';
CREATE INDEX IF NOT EXISTS idx_plugin_sessions_origin ON plugin_sessions(origin_host, origin_ref);

-- +migrate Dialect sqlite
SELECT 1; -- SQLite dev schema is expanded by the ORM fixture.
