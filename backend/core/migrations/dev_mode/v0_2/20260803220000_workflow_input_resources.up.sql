CREATE TABLE IF NOT EXISTS workflow_input_resources (
    id varchar(36) PRIMARY KEY,
    owner_user_id varchar(255) NOT NULL,
    name varchar(255) NOT NULL,
    mime_type varchar(255) NOT NULL,
    size bigint NOT NULL,
    content_hash varchar(80) NOT NULL,
    revision bigint NOT NULL DEFAULT 1,
    content blob NOT NULL,
    created_at datetime NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_workflow_input_resources_owner_hash
    ON workflow_input_resources(owner_user_id, content_hash);

CREATE TABLE IF NOT EXISTS workflow_input_bindings (
    id varchar(36) PRIMARY KEY,
    workflow_session_id varchar(36) NOT NULL,
    material_id varchar(64) NOT NULL,
    resource_type varchar(32) NOT NULL,
    resource_id varchar(36) NOT NULL,
    resource_revision bigint NOT NULL,
    content_hash varchar(80) NOT NULL,
    validity varchar(16) NOT NULL DEFAULT 'effective',
    created_by_command_id varchar(64) NOT NULL,
    created_at datetime NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_workflow_input_bindings_session
    ON workflow_input_bindings(workflow_session_id);
CREATE INDEX IF NOT EXISTS idx_workflow_input_bindings_resource
    ON workflow_input_bindings(resource_id);

ALTER TABLE plugin_attempt_input_bindings ADD COLUMN source_type varchar(32) NOT NULL DEFAULT 'artifact';
ALTER TABLE plugin_attempt_input_bindings ADD COLUMN source_id varchar(128) NOT NULL DEFAULT '';
ALTER TABLE plugin_attempt_input_bindings ADD COLUMN source_revision varchar(64) NOT NULL DEFAULT '';
ALTER TABLE plugin_attempt_input_bindings ADD COLUMN content_hash varchar(80) NOT NULL DEFAULT '';
